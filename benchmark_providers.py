"""Explicit, tiny provider probe; never runs during normal study clicks.

Run with ``python benchmark_providers.py``. At most one completion per configured
provider receives the identical fictional exercise below, not a student's
question or source material. Only sanitized timings/statuses are printed.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import time
import tomllib

from provider_router import (
    PROFILE_PATH, build_candidates, record_failure, record_success,
)
from provider_transport import ProviderError, complete, discover_gemini_models


BENCHMARK_SOURCE = "synthetic-benchmark"
BENCHMARK_PAGE = f"{BENCHMARK_SOURCE}, page 1"
SYNTHETIC_PROMPT = f"""This is a fictional, synthetic exercise for testing response format.
Use only these invented facts:
[{BENCHMARK_PAGE}]
The blue token has the label ALPHA. The green token has the label BETA.
The red token has the label GAMMA. The yellow token has the label DELTA.

Write exactly ONE MCQ asking for the label of the blue token.
Use the four options ALPHA, BETA, GAMMA, DELTA, once each, in any order.
Select the option supported by the fictional facts with a zero-based answer_index.
Include one short explanation. Do not use real medical or personal information.
Return ONLY a complete valid JSON array containing one object, without markdown:
[{{"question":"What is the label of the blue token?",
"options":["ALPHA","BETA","GAMMA","DELTA"],"answer_index":0,
"explanation":"The fictional source gives the blue token the label ALPHA.",
"page":"{BENCHMARK_PAGE}"}}]
"""

_PROVIDER_LABELS = {"cerebras": "Cerebras", "groq": "Groq", "gemini": "Gemini"}
_FAILURE_KINDS = frozenset({"auth", "rate_limit", "model", "timeout", "unavailable", "invalid"})


def validate_synthetic_mcq(text):
    """Check the complete JSON and its known answer, rather than syntax alone."""
    if not isinstance(text, str):
        return False
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return False
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        return False
    item = data[0]
    question = item.get("question")
    options = item.get("options")
    index = item.get("answer_index")
    explanation = item.get("explanation")
    if (not isinstance(question, str) or not question.strip()
            or not isinstance(options, list) or len(options) != 4
            or not all(isinstance(option, str) and option.strip() for option in options)
            or type(index) is not int or not 0 <= index <= 3
            or not isinstance(explanation, str) or not explanation.strip()
            or item.get("page") != BENCHMARK_PAGE):
        return False
    words = set(re.findall(r"[a-z]+", question.casefold()))
    if not {"blue", "token", "label"} <= words or words & {"not", "except", "incorrect", "false"}:
        return False
    normalized = [option.strip().casefold() for option in options]
    return set(normalized) == {"alpha", "beta", "gamma", "delta"} and normalized[index] == "alpha"


def _one_per_provider(candidates):
    selected, providers = [], set()
    for candidate in candidates:
        provider = candidate.provider.casefold()
        if provider in _PROVIDER_LABELS and provider not in providers:
            selected.append(candidate)
            providers.add(provider)
        if len(selected) == 3:
            break
    return selected


def run_benchmark(candidates, *, completion_fn=None):
    """Return (private profile, sanitized rows), with at most three completions.

    An injectable completion function permits fully offline tests. The executor
    waits for all bounded transports before returning; no background probe is
    left running when the benchmark exits.
    """
    call = complete if completion_fn is None else completion_fn
    selected = _one_per_provider(candidates)
    state = {"schema": 1, "created_at": time.time(), "stats": {}, "cooldowns": {}}
    rows = []
    if not selected:
        return state, ()

    def probe(candidate):
        started = time.perf_counter()
        try:
            result = call(candidate, SYNTHETIC_PROMPT, max_tokens=400,
                          temperature=0.0, timeout_seconds=20.0)
            if (not isinstance(result.text, str) or not math.isfinite(result.elapsed)
                    or result.elapsed < 0 or not validate_synthetic_mcq(result.text)):
                raise ProviderError("Synthetic response failed validation.", kind="invalid")
            return result, None, result.elapsed
        except ProviderError as error:
            # Even a custom transport's message is never printed or persisted.
            kind = error.kind if error.kind in _FAILURE_KINDS else "unavailable"
            sanitized = ProviderError("The provider probe failed.", kind=kind,
                                      status_code=error.status_code, retry_after=error.retry_after)
            return None, sanitized, time.perf_counter() - started
        except Exception:
            return None, ProviderError("The provider probe failed.", kind="unavailable"), time.perf_counter() - started

    # Each worker submits one identical completion only; no fallback/retry loop.
    with ThreadPoolExecutor(max_workers=len(selected)) as executor:
        futures = {executor.submit(probe, candidate): candidate for candidate in selected}
        for future in as_completed(futures):
            candidate = futures[future]
            result, error, elapsed = future.result()
            if error is None:
                record_success(state, candidate, result, task="mcq")
                status = "valid"
            else:
                record_failure(state, candidate, error, task="mcq")
                status = error.kind
            rows.append({"provider": _PROVIDER_LABELS[candidate.provider.casefold()],
                         "model": candidate.model, "seconds": round(elapsed, 3),
                         "status": status, "valid_json": error is None})
    order = {label: index for index, label in enumerate(_PROVIDER_LABELS.values())}
    rows.sort(key=lambda row: order[row["provider"]])
    return state, tuple(rows)


def _usable_key(value):
    value = value.strip() if isinstance(value, str) else ""
    if len(value) < 12 or "PASTE" in value.upper() or "YOUR-KEY" in value.upper():
        return ""
    return value


def _configured_keys():
    # Credentials are read only when this explicit command runs, never at import.
    try:
        path = Path(__file__).with_name(".streamlit") / "secrets.toml"
        with path.open("rb") as handle:
            secrets = tomllib.load(handle)
    except (OSError, ValueError):
        secrets = {}

    def key(name):
        return _usable_key(secrets.get(name)) or _usable_key(os.environ.get(name))

    groq_keys = tuple(dict.fromkeys(key(name) for name in
                                  ("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3",
                                   "GROQ_API_KEY_4", "GROQ_API_KEY_5") if key(name)))
    return groq_keys, key("CEREBRAS_API_KEY"), key("GEMINI_API_KEY")


@lru_cache(maxsize=1)
def _benchmark_gemini_models(key):
    return tuple(discover_gemini_models(key, timeout_seconds=4.0))


def _save_profile(profile):
    path = Path(__file__).parent / PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(profile, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    groq_keys, cerebras_key, gemini_key = _configured_keys()
    gemini_models = None
    if gemini_key:
        try:
            discovered = _benchmark_gemini_models(gemini_key)
            if discovered:
                gemini_models = discovered
        except Exception:
            # Discovery failure retains the router's stable model defaults.
            pass
    candidates = build_candidates(groq_keys=groq_keys[:1], cerebras_key=cerebras_key,
                                  gemini_key=gemini_key, task="mcq", gemini_models=gemini_models)
    profile, rows = run_benchmark(candidates)
    profile_saved = True
    for row in rows:
        print(json.dumps(row, ensure_ascii=True, allow_nan=False))
    if rows:
        try:
            _save_profile(profile)
        except (OSError, ValueError):
            print(json.dumps({"provider": "Local profile", "model": "none", "seconds": 0,
                              "status": "not_saved", "valid_json": False}))
            profile_saved = False
    else:
        print(json.dumps({"provider": "none", "model": "none", "seconds": 0,
                          "status": "not_configured", "valid_json": False}))
    print("This short synthetic MCQ probe does not measure a full study answer or a 40-question quiz.")
    return 0 if profile_saved and any(row["valid_json"] for row in rows) else 1


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:
        # An unexpected local failure must not expose a provider exception.
        print(json.dumps({"provider": "Benchmark", "model": "none", "seconds": 0,
                          "status": "unavailable", "valid_json": False}))
        exit_code = 1
    raise SystemExit(exit_code)

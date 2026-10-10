"""Prefer recent valid, fast answers and skip temporarily unhealthy APIs.

No requests are made at import time. Normal study clicks run one sequential
provider attempt at a time; a benchmark is an explicit, separate operation.
"""

from hashlib import sha256
import json
from pathlib import Path
import time

from provider_transport import Candidate, ProviderError, complete, discover_gemini_models


GROQ_STUDY_MODEL = "openai/gpt-oss-120b"
GROQ_MCQ_MODEL = "openai/gpt-oss-20b"
CEREBRAS_MODELS = ("gpt-oss-120b", "qwen-3.8-27b")
GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash")
PROFILE_PATH = "tmp/provider-speed-profile.json"
PROFILE_TTL = 3600
CALL_BUDGET = 60.0
ATTEMPT_BUDGET = 25.0
MAX_ATTEMPTS = 5


def credential_id(provider, key):
    # Changing a key creates a new scope. Credentials never enter the profile,
    # diagnostics, labels, or exception messages.
    return provider + ":" + sha256(key.encode("utf-8")).hexdigest()[:16]


def build_candidates(*, groq_keys=(), cerebras_key="", gemini_key="", task="mcq", gemini_models=None):
    candidates = []

    def add(provider, model, key, label):
        candidates.append(Candidate(credential_id(provider, key) + ":" + model,
                                    provider, model, key, label))

    # Current, quality-appropriate models. The default order is a starting
    # point; observed valid response timings take precedence over this order.
    if cerebras_key:
        add("cerebras", CEREBRAS_MODELS[0], cerebras_key, "Cerebras")
    groq_models = (GROQ_MCQ_MODEL, GROQ_STUDY_MODEL) if task == "mcq" else (GROQ_STUDY_MODEL,)
    keys = tuple(dict.fromkeys(key for key in groq_keys if key))
    if keys:
        add("groq", groq_models[0], keys[0], "Groq")
    models = tuple(gemini_models) if gemini_models is not None else GEMINI_MODELS
    if gemini_key and models:
        add("gemini", models[0], gemini_key, "Gemini")
    if cerebras_key:
        add("cerebras", CEREBRAS_MODELS[1], cerebras_key, "Cerebras")
    for key in keys[1:]:
        add("groq", groq_models[0], key, "Groq")
    for model in groq_models[1:]:
        for key in keys:
            add("groq", model, key, "Groq")
    if gemini_key:
        for model in models[1:3]:
            add("gemini", model, gemini_key, "Gemini")
    return candidates


def _scopes(candidate, task):
    return ("key:" + credential_id(candidate.provider, candidate.api_key),
            "provider:" + candidate.provider,
            "model:" + candidate.id,
            "quality:" + candidate.id + ":" + task)


def is_ready(state, candidate, task, now=None):
    now = time.time() if now is None else now
    cooldowns = state.get("cooldowns", {})
    return all(cooldowns.get(scope, 0) <= now for scope in _scopes(candidate, task))


def record_failure(state, candidate, error, task="mcq", now=None):
    now = time.time() if now is None else now
    key_scope, provider_scope, model_scope, quality_scope = _scopes(candidate, task)
    if error.kind == "auth":
        scope, seconds = key_scope, 7200
    elif error.kind == "rate_limit":
        # Do not sleep or retry an exhausted key in the next MCQ batch.
        scope, seconds = key_scope, max(60, min(error.retry_after or 0, 86400))
    elif error.kind == "model":
        scope, seconds = model_scope, 21600
    elif error.kind == "invalid":
        scope, seconds = quality_scope, 60
    else:
        # A service/network timeout affects its other models and keys too.
        scope, seconds = provider_scope, 30
    cooldowns = state.setdefault("cooldowns", {})
    cooldowns[scope] = max(cooldowns.get(scope, 0), now + seconds)


def record_success(state, candidate, result, task="mcq", now=None):
    now = time.time() if now is None else now
    tasks = state.setdefault("stats", {}).setdefault(candidate.id, {})
    old = tasks.get(task, {})
    # Compare like tasks without favoring a short answer over a larger batch.
    # This is observed end-to-end valid response time, not advertised throughput.
    speed = max(result.elapsed, .001) * 1000 / max(len(result.text), 100)
    previous = old.get("seconds_per_1000_chars", speed)
    tasks[task] = {"samples": old.get("samples", 0) + 1,
                   "seconds_per_1000_chars": .4 * speed + .6 * previous,
                   "elapsed": result.elapsed, "updated_at": now}
    cooldowns = state.setdefault("cooldowns", {})
    for scope in _scopes(candidate, task):
        cooldowns.pop(scope, None)


def _timing(state, candidate, task, now):
    tasks = state.get("stats", {}).get(candidate.id, {})
    observation = tasks.get(task)
    if observation and now - observation.get("updated_at", 0) < PROFILE_TTL:
        return 0, observation["seconds_per_1000_chars"]
    # A short MCQ probe is only a starting hint for other tasks; actual task
    # observations outrank it. Model eligibility still preserves study quality.
    recent = [entry for entry in tasks.values()
              if now - entry.get("updated_at", 0) < PROFILE_TTL]
    if recent:
        return 1, sum(entry["seconds_per_1000_chars"] for entry in recent) / len(recent)
    return 2, 0


def ranked_candidates(candidates, state, task, now=None):
    now = time.time() if now is None else now
    ready = [candidate for candidate in candidates if is_ready(state, candidate, task, now)]
    # Stable sorting retains the configured fallback order on a tie.
    return sorted(ready, key=lambda candidate: _timing(state, candidate, task, now))


def load_speed_profile(path=PROFILE_PATH):
    """Read fresh local measurements only; missing/invalid files are harmless."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        now = time.time()
        if data.get("schema") != 1 or not 0 <= now - data["created_at"] < PROFILE_TTL:
            return {}
        stats = {}
        for candidate_id, tasks in data.get("stats", {}).items():
            accepted = {}
            for task, entry in tasks.items():
                speed = entry["seconds_per_1000_chars"]
                if (isinstance(speed, (int, float)) and 0 < speed < 10000
                        and 0 <= now - entry["updated_at"] < PROFILE_TTL):
                    accepted[task] = entry
            if accepted:
                stats[candidate_id] = accepted
        cooldowns = {scope: until for scope, until in data.get("cooldowns", {}).items()
                     if isinstance(until, (int, float)) and now < until <= now + 86400}
        return {"stats": stats, "cooldowns": cooldowns}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def route_completion(prompt, *, groq_keys=(), cerebras_key="", gemini_key="", state=None,
                     task="topic", max_tokens=2000, temperature=.3, validator=None, deadline=None):
    """Return one validated answer, learning its speed for subsequent requests."""
    state = {} if state is None else state
    end = min(deadline if deadline is not None else float("inf"), time.monotonic() + CALL_BUDGET)
    attempted = set()
    discovered = False
    gemini_models = None
    count = 0
    while count < MAX_ATTEMPTS and end - time.monotonic() > .25:
        candidates = build_candidates(groq_keys=groq_keys, cerebras_key=cerebras_key,
                                      gemini_key=gemini_key, task=task, gemini_models=gemini_models)
        ready = [candidate for candidate in ranked_candidates(candidates, state, task)
                 if candidate.id not in attempted]
        if not ready:
            break
        candidate = ready[0]
        if candidate.provider == "gemini" and not discovered:
            discovered = True
            scope = credential_id("gemini", gemini_key)
            cached = state.get("gemini_models", {}).get(scope)
            if cached and cached["expires"] > time.time():
                gemini_models = cached["models"]
            else:
                # Lookup happens only if Gemini is needed. Failed lookups retain
                # the current stable defaults rather than blocking generation.
                try:
                    gemini_models = discover_gemini_models(gemini_key, min(4, end - time.monotonic()))
                    if not gemini_models:
                        gemini_models = list(GEMINI_MODELS)
                    state.setdefault("gemini_models", {})[scope] = {
                        "models": gemini_models, "expires": time.time() + PROFILE_TTL}
                except ProviderError as error:
                    if error.kind in ("auth", "rate_limit"):
                        record_failure(state, candidate, error, task)
                    else:
                        state.setdefault("gemini_models", {})[scope] = {
                            "models": list(GEMINI_MODELS), "expires": time.time() + 60}
                    gemini_models = list(GEMINI_MODELS)
            continue
        remaining = end - time.monotonic()
        if remaining <= .25:
            break
        attempted.add(candidate.id)
        count += 1
        attempt_budget = min(ATTEMPT_BUDGET, remaining)
        try:
            result = complete(candidate, prompt, max_tokens, temperature, attempt_budget)
            try:
                valid = result.text.strip() and (validator is None or validator(result.text))
            except Exception:
                valid = False
            if not valid:
                raise ProviderError("The provider returned no usable answer.", kind="invalid")
        except ProviderError as error:
            record_failure(state, candidate, error, task)
            continue
        record_success(state, candidate, result, task)
        state["last_result"] = {"provider": result.provider, "model": result.model,
                                "elapsed": result.elapsed, "task": task}
        return result
    raise RuntimeError("AI providers are unavailable, busy, or returned no valid answer. Try again shortly.")

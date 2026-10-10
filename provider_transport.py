"""Single-attempt REST transports with bounded waits and sanitized failures.

No credentials are read and no network calls occur when this module is imported.
Model support was checked against the providers' official API references:
https://inference-docs.cerebras.ai/capabilities/reasoning
https://console.groq.com/docs/api-reference
https://ai.google.dev/api/models
https://ai.google.dev/gemini-api/docs/generate-content/thinking
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re
import time

import requests


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    provider: str
    model: str
    api_key: str = field(repr=False)
    label: str


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    provider: str
    model: str
    elapsed: float
    output_tokens: int


class ProviderError(Exception):
    """A public failure with no provider body, credentials, or request details."""

    def __init__(self, message, *, kind, status_code=None, retry_after=None):
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retry_after = retry_after


_MESSAGES = {
    "auth": "Provider authentication failed.",
    "rate_limit": "Provider rate limit reached.",
    "model": "The requested model is unavailable.",
    "timeout": "Provider request timed out.",
    "unavailable": "Provider is temporarily unavailable.",
    "invalid": "Provider returned an invalid or incomplete response.",
}
_CHAT_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
}
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _failure(kind, status_code=None, retry_after=None):
    return ProviderError(_MESSAGES[kind], kind=kind, status_code=status_code, retry_after=retry_after)


def _budget(seconds, cap=60.0):
    try:
        seconds = float(seconds)
    except (ValueError, TypeError):
        raise _failure("invalid") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise _failure("timeout") from None
    return min(seconds, cap)


def _timeout(seconds):
    # The sum remains within the caller's per-attempt budget. Requests timeouts
    # bound connection setup and socket inactivity, rather than a hard wall clock.
    seconds = _budget(seconds)
    connect = min(2.0, seconds / 4)
    return connect, seconds - connect


def _retry_after(value):
    if value is None:
        return None
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else None
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(str(value))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _error_kind(status, data):
    error = data.get("error", {}) if isinstance(data, dict) else {}
    if not isinstance(error, dict):
        error = {}
    code = str(error.get("code", error.get("status", ""))).lower()
    message = str(error.get("message", "")).lower()
    if status in (401, 403) or code in ("invalid_api_key", "unauthenticated", "permission_denied"):
        return "auth"
    if status in (402, 429) or code in ("rate_limit_exceeded", "resource_exhausted"):
        return "rate_limit"
    if status in (404, 410) or code in ("model_not_found", "model_decommissioned", "unsupported_model"):
        return "model"
    if status in (408, 504):
        return "timeout"
    if status in (400, 422) and re.search(r"\bmodel\b.*(?:not found|does not exist|decommission|not supported)", message):
        return "model"
    return "unavailable" if status >= 500 or 300 <= status < 400 else "invalid"


def _json_response(response):
    status = response.status_code
    if not 200 <= status < 300:
        try:
            body = response.json()
        except (ValueError, TypeError):
            body = None
        wait = _retry_after(response.headers.get("Retry-After"))
        if status == 402:
            # A credential quota failure applies to every model using that key;
            # the router can suppress repeated attempts for at least an hour.
            wait = max(wait or 0, 3600.0)
        raise _failure(_error_kind(status, body), status, wait) from None
    try:
        body = response.json()
    except (ValueError, TypeError):
        raise _failure("invalid", status) from None
    if not isinstance(body, dict) or "error" in body:
        raise _failure("invalid", status) from None
    return body


def _request(method, url, *, timeout_seconds, **kwargs):
    try:
        # Do not follow redirects: each completion gets exactly one HTTP attempt,
        # and API-key headers remain on their intended provider's endpoint.
        response = method(url, timeout=_timeout(timeout_seconds), allow_redirects=False, **kwargs)
    except requests.Timeout:
        raise _failure("timeout") from None
    except requests.RequestException:
        raise _failure("unavailable") from None
    return _json_response(response)


def _token_count(usage, name):
    value = usage.get(name, 0) if isinstance(usage, dict) else 0
    return value if type(value) is int and value >= 0 else 0


def _chat_text(data):
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise _failure("invalid")
    choice = choices[0]
    if choice.get("finish_reason") not in (None, "stop"):
        raise _failure("invalid")
    message = choice.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise _failure("invalid")
    return text.strip(), _token_count(data.get("usage"), "completion_tokens")


def _gemini_text(data):
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise _failure("invalid")
    candidate = candidates[0]
    if candidate.get("finishReason") not in (None, "STOP"):
        raise _failure("invalid")
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise _failure("invalid")
    text_parts = []
    for part in parts:
        if not isinstance(part, dict):
            raise _failure("invalid")
        if part.get("thought") is True:
            continue
        if "text" in part:
            if not isinstance(part["text"], str):
                raise _failure("invalid")
            text_parts.append(part["text"])
    text = "".join(text_parts).strip()
    if not text:
        raise _failure("invalid")
    return text, _token_count(data.get("usageMetadata"), "candidatesTokenCount")


def _gemini_thinking(model):
    # Only set parameters documented for the exact known families. Discovery
    # can return future families, which should use their supported defaults.
    stable = re.sub(r"-\d{3}$", "", model)
    if stable in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
        return {"thinkingBudget": 0}
    if stable in ("gemini-3-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"):
        return {"thinkingLevel": "minimal"}
    if stable == "gemini-3.8-flash":
        return {"thinkingLevel": "low"}
    return None


def complete(candidate, prompt, max_tokens, temperature, timeout_seconds):
    """Make one bounded completion attempt or raise a sanitized ProviderError."""
    if not isinstance(candidate, Candidate) or not isinstance(candidate.provider, str):
        raise _failure("invalid")
    provider = candidate.provider.lower()
    model = candidate.model
    if provider not in (*_CHAT_URLS, "gemini") or not isinstance(model, str) or not model.strip():
        raise _failure("invalid")
    if not isinstance(candidate.api_key, str) or not candidate.api_key.strip():
        raise _failure("auth")
    if not isinstance(prompt, str) or not prompt.strip() or type(max_tokens) is not int or max_tokens < 1:
        raise _failure("invalid")
    if not isinstance(temperature, (int, float)) or not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise _failure("invalid")
    seconds = _budget(timeout_seconds)
    started = time.monotonic()

    if provider == "gemini":
        model = model.removeprefix("models/")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", model):
            raise _failure("invalid")
        generation = {"maxOutputTokens": max_tokens, "temperature": temperature}
        thinking = _gemini_thinking(model)
        if thinking is not None:
            generation["thinkingConfig"] = thinking
        body = _request(requests.post, f"{_GEMINI_URL}/{model}:generateContent",
                        timeout_seconds=seconds,
                        headers={"x-goog-api-key": candidate.api_key, "Content-Type": "application/json"},
                        json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                              "generationConfig": generation})
        text, tokens = _gemini_text(body)
    else:
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "max_completion_tokens": max_tokens, "temperature": temperature, "stream": False}
        supported = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"} if provider == "groq" else {"gpt-oss-120b", "qwen-3.8-27b"}
        if model in supported:
            payload["reasoning_effort"] = "low"
        body = _request(requests.post, _CHAT_URLS[provider], timeout_seconds=seconds,
                        headers={"Authorization": f"Bearer {candidate.api_key}", "Content-Type": "application/json"},
                        json=payload)
        text, tokens = _chat_text(body)
    return Completion(text, candidate.label, model, max(0.0, time.monotonic() - started), tokens)


def _gemini_model_rank(model):
    version = re.search(r"^gemini-(\d+)(?:\.(\d+))?-", model)
    major, minor = (int(version[1]), int(version[2] or 0)) if version else (0, 0)
    return (0 if "flash-lite" in model else 1, -major, -minor, model)


def _text_flash_model(entry):
    if not isinstance(entry, dict):
        return None
    methods = entry.get("supportedGenerationMethods")
    if not isinstance(methods, list) or "generateContent" not in methods:
        return None
    name = entry.get("name")
    if not isinstance(name, str):
        return None
    name = name.removeprefix("models/")
    if not re.fullmatch(r"gemini-(?:\d+(?:\.\d+)?-flash(?:-lite)?(?:-\d{3})?|flash(?:-lite)?-latest)", name):
        return None
    modalities = entry.get("outputModalities")
    if isinstance(modalities, list) and any(str(value).upper() != "TEXT" for value in modalities):
        return None
    return name


def discover_gemini_models(api_key, timeout_seconds=4.0):
    """List stable text Flash-Lite then Flash IDs under a four-second budget.

    Pagination is complete, with repeated tokens rejected. Callers own caching;
    this function reads no secrets and has no side effects beyond its GET calls.
    """
    if not isinstance(api_key, str) or not api_key.strip():
        raise _failure("auth")
    deadline = time.monotonic() + _budget(timeout_seconds, cap=4.0)
    names, seen_tokens = set(), set()
    page_token = None
    for _ in range(20):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _failure("timeout")
        params = {"pageSize": 1000}
        if page_token is not None:
            params["pageToken"] = page_token
        data = _request(requests.get, _GEMINI_URL, timeout_seconds=remaining,
                        headers={"x-goog-api-key": api_key}, params=params)
        entries = data.get("models", [])
        if not isinstance(entries, list):
            raise _failure("invalid")
        for entry in entries:
            model = _text_flash_model(entry)
            if model:
                names.add(model)
        page_token = data.get("nextPageToken")
        if not page_token:
            return sorted(names, key=_gemini_model_rank)
        if not isinstance(page_token, str) or page_token in seen_tokens:
            raise _failure("invalid")
        seen_tokens.add(page_token)
    raise _failure("invalid")

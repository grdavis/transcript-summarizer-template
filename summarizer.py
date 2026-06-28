"""Shared Gemini helpers for pipeline jobs."""

from __future__ import annotations

import os
import random
import sys
import time

from google import genai
from google.genai import errors as genai_errors

MAX_GEMINI_ATTEMPTS = 8
GEMINI_RETRY_BASE_SEC = 3.0
DEFAULT_MODELS = ["gemini-3-flash-preview", "gemini-2.5-flash"]

_exhausted_models: set[str] = set()


def _parse_model_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _get_models() -> list[str]:
    models_raw = os.environ.get("GEMINI_MODELS")
    if models_raw:
        return _parse_model_list(models_raw)
    legacy = os.environ.get("GEMINI_MODEL")
    if legacy and legacy.strip():
        return [legacy.strip()]
    return list(DEFAULT_MODELS)


def _available_models() -> list[str]:
    return [model for model in _get_models() if model not in _exhausted_models]


def _quota_failure_violations(exc: BaseException) -> list[dict]:
    details_payload = getattr(exc, "details", None)
    if not isinstance(details_payload, dict):
        return []
    error_details = details_payload.get("error", {}).get("details", [])
    if not isinstance(error_details, list):
        return []
    violations: list[dict] = []
    for detail in error_details:
        if not isinstance(detail, dict):
            continue
        detail_type = detail.get("@type", "")
        if not detail_type.endswith("QuotaFailure"):
            continue
        for violation in detail.get("violations", []):
            if isinstance(violation, dict):
                violations.append(violation)
    return violations


def _is_daily_quota_exhausted(exc: BaseException) -> bool:
    if getattr(exc, "code", None) != 429:
        return False

    for violation in _quota_failure_violations(exc):
        quota_id = str(violation.get("quotaId", ""))
        quota_metric = str(violation.get("quotaMetric", ""))
        if "PerDay" in quota_id or "PerDay" in quota_metric:
            return True

    message = str(getattr(exc, "message", "") or exc)
    message_lower = message.lower()
    if "perday" in message_lower.replace("_", "").replace("-", ""):
        return True
    if "requests per day" in message_lower:
        return True
    return False


def _gemini_error_retryable(exc: BaseException) -> bool:
    if _is_daily_quota_exhausted(exc):
        return False
    if isinstance(exc, genai_errors.ServerError):
        code = getattr(exc, "code", None)
        return code in (408, 429, 500, 502, 503, 504)
    if isinstance(exc, genai_errors.ClientError):
        return getattr(exc, "code", None) == 429
    # Transient transport errors from the HTTP client underneath google-genai.
    exc_name = type(exc).__name__
    if exc_name in {"RemoteProtocolError", "ReadTimeout", "ConnectTimeout", "ConnectError"}:
        return True
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    return False


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return genai.Client(api_key=api_key)


def _sleep_before_retry(label: str, attempt: int, reason: str) -> None:
    cap = 90.0
    delay = min(GEMINI_RETRY_BASE_SEC * (2 ** (attempt - 1)), cap)
    jitter = random.uniform(0.0, delay * 0.25)
    sleep_s = delay + jitter
    print(
        f"{label} {reason}; backing off {sleep_s:.1f}s "
        f"(attempt {attempt}/{MAX_GEMINI_ATTEMPTS})...",
        file=sys.stderr,
    )
    time.sleep(sleep_s)


def generate_content(prompt: str, *, label: str = "Gemini") -> str:
    models = _available_models()
    if not models:
        raise RuntimeError(f"{label} failed: all configured Gemini models exhausted for today")

    client = _get_client()

    last_error: BaseException | None = None
    for model_index, model in enumerate(models):
        for attempt in range(1, MAX_GEMINI_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                text = response.text
                if not text:
                    raise RuntimeError(f"{label} returned empty response")
                return text
            except (genai_errors.ServerError, genai_errors.ClientError) as exc:
                last_error = exc
                if _is_daily_quota_exhausted(exc):
                    _exhausted_models.add(model)
                    if model_index + 1 < len(models):
                        next_model = models[model_index + 1]
                        print(
                            f"{label}: {model} daily quota exhausted; "
                            f"falling back to {next_model}",
                            file=sys.stderr,
                        )
                        break
                    raise
                if not _gemini_error_retryable(exc) or attempt >= MAX_GEMINI_ATTEMPTS:
                    raise
                status = getattr(exc, "status", None) or "error"
                _sleep_before_retry(
                    label,
                    attempt,
                    f"returned {exc.code} ({status})",
                )
            except Exception as exc:
                last_error = exc
                if not _gemini_error_retryable(exc) or attempt >= MAX_GEMINI_ATTEMPTS:
                    raise
                _sleep_before_retry(label, attempt, f"hit {type(exc).__name__}")

    if last_error:
        raise last_error
    raise RuntimeError(f"{label} failed after {MAX_GEMINI_ATTEMPTS} attempts")


def classify(text: str, question: str) -> bool:
    """Return True when Gemini answers YES to a yes/no question about text."""
    snippet = text[:12000]
    prompt = f"""Answer with exactly one word: YES or NO.

Question: {question}

Text:
{snippet}
"""
    answer = generate_content(prompt, label="Gemini classify").strip().upper()
    return answer.startswith("YES")

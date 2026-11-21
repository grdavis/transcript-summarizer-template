"""Shared Gemini helpers for pipeline jobs."""

from __future__ import annotations

import os
import random
import sys
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

MAX_GEMINI_ATTEMPTS = 8
MAX_503_RETRIES_BEFORE_FALLBACK = 4
# Transport hangs (RemoteProtocolError / timeouts) burned yesterday's and today's
# runs; fail over to the next model after a few attempts instead of sitting for
# the full attempt budget.
MAX_TRANSPORT_RETRIES_BEFORE_FALLBACK = 3
GEMINI_RETRY_BASE_SEC = 3.0
# Cap a single generate_content HTTP call so a stalled stream cannot eat the
# whole Actions job timeout (default 2 minutes).
DEFAULT_HTTP_TIMEOUT_MS = 120_000
# Aliases Google hot-swaps to the current Flash and Flash-Lite releases.
# There is no bare "gemini" id. Numbered ids (gemini-3.8-flash, and so on)
# stay put until this list or GEMINI_MODELS is edited.
DEFAULT_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]

_TRANSPORT_ERROR_NAMES = frozenset(
    {
        "RemoteProtocolError",
        "ReadTimeout",
        "WriteTimeout",
        "ConnectTimeout",
        "PoolTimeout",
        "ConnectError",
        "TimeoutException",
    }
)

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


def _http_timeout_ms() -> int:
    """Return per-request HTTP timeout in milliseconds."""
    raw = os.environ.get("GEMINI_HTTP_TIMEOUT_MS", "").strip()
    if not raw:
        return DEFAULT_HTTP_TIMEOUT_MS
    try:
        timeout = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"GEMINI_HTTP_TIMEOUT_MS must be a positive integer (milliseconds), got {raw!r}"
        ) from exc
    if timeout <= 0:
        raise ValueError(
            f"GEMINI_HTTP_TIMEOUT_MS must be a positive integer (milliseconds), got {timeout}"
        )
    return timeout


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


def _is_transport_error(exc: BaseException) -> bool:
    """True for stalled/dropped HTTP connections from the client stack."""
    if type(exc).__name__ in _TRANSPORT_ERROR_NAMES:
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    # httpx wraps some failures as OSError subclasses; keep parity with prior behavior.
    if isinstance(exc, OSError) and not isinstance(exc, genai_errors.APIError):
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
    return _is_transport_error(exc)


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=_http_timeout_ms()),
    )


def _max_attempts_for_error(exc: BaseException) -> int:
    """503/502 may clear on retry — try a few times, then switch models.
    Transport stalls get a shorter budget so we fall back before the job times out.
    Daily-quota 429 skips retries entirely (handled before this is called)."""
    if isinstance(exc, genai_errors.ServerError) and getattr(exc, "code", None) in (502, 503):
        return MAX_503_RETRIES_BEFORE_FALLBACK
    if _is_transport_error(exc):
        return MAX_TRANSPORT_RETRIES_BEFORE_FALLBACK
    return MAX_GEMINI_ATTEMPTS


def _sleep_before_retry(label: str, attempt: int, reason: str, *, max_attempts: int) -> None:
    cap = 90.0
    delay = min(GEMINI_RETRY_BASE_SEC * (2 ** (attempt - 1)), cap)
    jitter = random.uniform(0.0, delay * 0.25)
    sleep_s = delay + jitter
    print(
        f"{label} {reason}; backing off {sleep_s:.1f}s "
        f"(attempt {attempt}/{max_attempts})...",
        file=sys.stderr,
        flush=True,
    )
    time.sleep(sleep_s)


def generate_content(
    prompt: str,
    *,
    label: str = "Gemini",
    models: list[str] | None = None,
    attempt_budget: int | None = None,
) -> str:
    """Generate text with Gemini.

    `models` pins this call to an explicit list and does not consult the
    session-wide exhausted set. Leave it unset for the production fallback chain
    (`GEMINI_MODELS`, then `GEMINI_MODEL`, then `DEFAULT_MODELS`).
    `attempt_budget` caps retries for one call; production leaves it unset.
    """
    if attempt_budget is not None and attempt_budget < 1:
        raise ValueError(f"attempt_budget must be a positive integer, got {attempt_budget}")

    if models is None:
        model_list = _available_models()
    else:
        model_list = [model.strip() for model in models if model and model.strip()]
    if not model_list:
        raise RuntimeError(f"{label} failed: all configured Gemini models exhausted for today")

    client = _get_client()
    attempt_limit = MAX_GEMINI_ATTEMPTS if attempt_budget is None else attempt_budget

    last_error: BaseException | None = None
    for model_index, model in enumerate(model_list):
        for attempt in range(1, attempt_limit + 1):
            try:
                print(
                    f"{label}: requesting {model} (attempt {attempt})...",
                    file=sys.stderr,
                    flush=True,
                )
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
                    if model_index + 1 < len(model_list):
                        next_model = model_list[model_index + 1]
                        print(
                            f"{label}: {model} daily quota exhausted; "
                            f"falling back to {next_model}",
                            file=sys.stderr,
                            flush=True,
                        )
                        break
                    raise
                if not _gemini_error_retryable(exc):
                    raise
                max_attempts = _max_attempts_for_error(exc)
                if attempt_budget is not None:
                    max_attempts = min(max_attempts, attempt_budget)
                if attempt >= max_attempts:
                    if model_index + 1 < len(model_list):
                        next_model = model_list[model_index + 1]
                        print(
                            f"{label}: {model} failed after {attempt} attempt(s); "
                            f"falling back to {next_model}",
                            file=sys.stderr,
                            flush=True,
                        )
                        break
                    raise
                status = getattr(exc, "status", None) or "error"
                _sleep_before_retry(
                    label,
                    attempt,
                    f"returned {exc.code} ({status})",
                    max_attempts=max_attempts,
                )
            except Exception as exc:
                last_error = exc
                if not _gemini_error_retryable(exc):
                    raise
                max_attempts = _max_attempts_for_error(exc)
                if attempt_budget is not None:
                    max_attempts = min(max_attempts, attempt_budget)
                if attempt >= max_attempts:
                    if model_index + 1 < len(model_list):
                        next_model = model_list[model_index + 1]
                        print(
                            f"{label}: {model} failed after {attempt} attempt(s); "
                            f"falling back to {next_model}",
                            file=sys.stderr,
                            flush=True,
                        )
                        break
                    raise
                _sleep_before_retry(
                    label, attempt, f"hit {type(exc).__name__}", max_attempts=max_attempts
                )

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

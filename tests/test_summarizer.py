from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors as genai_errors

import summarizer


@pytest.fixture(autouse=True)
def reset_summarizer_state(monkeypatch: pytest.MonkeyPatch) -> None:
    summarizer._exhausted_models.clear()
    monkeypatch.delenv("GEMINI_MODELS", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def _quota_error(*, quota_id: str, message: str = "Quota exceeded") -> genai_errors.ClientError:
    payload = {
        "error": {
            "code": 429,
            "message": message,
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {
                            "quotaId": quota_id,
                            "quotaMetric": (
                                "generativelanguage.googleapis.com/generate_content_free_tier_requests"
                            ),
                        }
                    ],
                }
            ],
        }
    }
    try:
        genai_errors.ClientError.raise_error(429, payload, None)
    except genai_errors.ClientError as exc:
        return exc
    raise AssertionError("expected ClientError")


def _response_with_text(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


def test_get_models_defaults_when_unset() -> None:
    assert summarizer._get_models() == summarizer.DEFAULT_MODELS


def test_get_models_parses_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODELS", " model-a , model-b, ")
    assert summarizer._get_models() == ["model-a", "model-b"]


def test_get_models_prefers_gemini_models_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODELS", "model-a,model-b")
    monkeypatch.setenv("GEMINI_MODEL", "legacy-model")
    assert summarizer._get_models() == ["model-a", "model-b"]


def test_get_models_legacy_single_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert summarizer._get_models() == ["gemini-2.5-flash"]


def test_is_daily_quota_exhausted_true_for_per_day_quota_id() -> None:
    exc = _quota_error(quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    assert summarizer._is_daily_quota_exhausted(exc) is True


def test_is_daily_quota_exhausted_false_for_per_minute_only() -> None:
    exc = _quota_error(quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
    assert summarizer._is_daily_quota_exhausted(exc) is False


def test_is_daily_quota_exhausted_false_for_generic_message() -> None:
    try:
        genai_errors.ClientError.raise_error(
            429,
            {"error": {"code": 429, "message": "Resource exhausted. Please try again later."}},
            None,
        )
    except genai_errors.ClientError as exc:
        assert summarizer._is_daily_quota_exhausted(exc) is False
    else:
        raise AssertionError("expected ClientError")


def test_is_daily_quota_exhausted_true_for_message_with_requests_per_day() -> None:
    try:
        genai_errors.ClientError.raise_error(
            429,
            {"error": {"code": 429, "message": "Exceeded requests per day for model"}},
            None,
        )
    except genai_errors.ClientError as exc:
        assert summarizer._is_daily_quota_exhausted(exc) is True
    else:
        raise AssertionError("expected ClientError")


@patch("summarizer._get_client")
@patch("summarizer._sleep_before_retry")
def test_generate_content_falls_back_on_daily_quota(
    mock_sleep: MagicMock,
    mock_get_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_MODELS", "model-a,model-b")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _quota_error(quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier"),
        _response_with_text("fallback summary"),
    ]

    result = summarizer.generate_content("prompt", label="Test")

    assert result == "fallback summary"
    assert mock_client.models.generate_content.call_count == 2
    assert mock_client.models.generate_content.call_args_list[0].kwargs["model"] == "model-a"
    assert mock_client.models.generate_content.call_args_list[1].kwargs["model"] == "model-b"
    mock_sleep.assert_not_called()


@patch("summarizer._get_client")
@patch("summarizer._sleep_before_retry")
def test_generate_content_retries_rpm_quota_without_fallback(
    mock_sleep: MagicMock,
    mock_get_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_MODELS", "model-a,model-b")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    rpm_error = _quota_error(quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
    mock_client.models.generate_content.side_effect = [
        rpm_error,
        _response_with_text("ok after retry"),
    ]

    result = summarizer.generate_content("prompt", label="Test")

    assert result == "ok after retry"
    assert mock_client.models.generate_content.call_count == 2
    assert all(
        call.kwargs["model"] == "model-a"
        for call in mock_client.models.generate_content.call_args_list
    )
    mock_sleep.assert_called_once()


@patch("summarizer._get_client")
@patch("summarizer._sleep_before_retry")
def test_generate_content_skips_exhausted_model_in_session(
    mock_sleep: MagicMock,
    mock_get_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_MODELS", "model-a,model-b")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _quota_error(quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier"),
        _response_with_text("first call fallback"),
        _response_with_text("second call direct"),
    ]

    first = summarizer.generate_content("prompt 1", label="Test")
    second = summarizer.generate_content("prompt 2", label="Test")

    assert first == "first call fallback"
    assert second == "second call direct"
    assert mock_client.models.generate_content.call_count == 3
    assert mock_client.models.generate_content.call_args_list[0].kwargs["model"] == "model-a"
    assert mock_client.models.generate_content.call_args_list[1].kwargs["model"] == "model-b"
    assert mock_client.models.generate_content.call_args_list[2].kwargs["model"] == "model-b"
    mock_sleep.assert_not_called()


@patch("summarizer._get_client")
def test_generate_content_raises_when_all_models_exhausted(
    mock_get_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_MODELS", "model-a,model-b")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    daily_error = _quota_error(quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    mock_client.models.generate_content.side_effect = [daily_error, daily_error]

    with pytest.raises(genai_errors.ClientError):
        summarizer.generate_content("prompt", label="Test")

    assert mock_client.models.generate_content.call_count == 2


@patch("summarizer._get_client")
def test_generate_content_raises_when_all_models_already_exhausted(
    mock_get_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_MODELS", "model-a,model-b")
    summarizer._exhausted_models.update({"model-a", "model-b"})

    with pytest.raises(RuntimeError, match="all configured Gemini models exhausted"):
        summarizer.generate_content("prompt", label="Test")

    mock_get_client.assert_not_called()

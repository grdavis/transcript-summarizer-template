"""Tests for source implementations."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from zoneinfo import ZoneInfo

from gmail_client import EmailMessage
from jobs.sources import GmailSource, NprIndicatorSource, _save_npr_summary

TZ = ZoneInfo("America/Los_Angeles")


def _sample_email(uid: str = "100") -> EmailMessage:
    return EmailMessage(
        uid=uid,
        sender="Example Newsletter <newsletter@example.com>",
        subject="Today's AI news",
        received_at=datetime(2026, 6, 25, 7, 0, tzinfo=TZ),
        body="Lots of AI news and opinions.",
    )


@patch("jobs.sources.GmailClient")
def test_gmail_source_collects_and_formats(mock_client_cls):
    client = MagicMock()
    mock_client_cls.return_value = client
    client.fetch_from_senders.return_value = [_sample_email()]

    source = GmailSource(senders=["newsletter@example.com"])
    result = source.collect()

    assert result.has_content is True
    assert "FROM: Example Newsletter" in result.prompt_text
    assert "Lots of AI news" in result.prompt_text
    assert result.on_success is not None


@patch("jobs.sources.GmailClient")
def test_gmail_source_empty_inbox(mock_client_cls):
    client = MagicMock()
    mock_client_cls.return_value = client
    client.fetch_from_senders.return_value = []

    source = GmailSource(senders=["newsletter@example.com"])
    result = source.collect()

    assert result.has_content is False


@patch("jobs.sources.GmailClient")
def test_gmail_source_on_success_marks_read(mock_client_cls):
    fetch_client = MagicMock()
    mark_client = MagicMock()
    mock_client_cls.side_effect = [fetch_client, mark_client]
    fetch_client.fetch_from_senders.return_value = [_sample_email()]

    source = GmailSource(senders=["newsletter@example.com"])
    result = source.collect()
    assert result.on_success is not None
    result.on_success("ignored")

    mark_client.mark_as_read.assert_called_once_with(["100"])


def _episode(title: str = "Jobs report", slug: str = "jobs") -> dict:
    return {
        "title": title,
        "published": "2026-08-21",
        "transcript_url": f"https://example.com/{slug}",
    }


@patch("jobs.sources.fetch_transcript", return_value="Transcript text.")
@patch("jobs.sources.get_episodes_for_calendar_week")
def test_npr_source_collects_transcripts(mock_get_episodes, mock_fetch):
    mock_get_episodes.return_value = [_episode()]

    source = NprIndicatorSource()
    result = source.collect()

    assert result.has_content is True
    assert "EPISODE: Jobs report" in result.prompt_text
    assert "Transcript text." in result.prompt_text
    assert result.on_success is not None


@patch("jobs.sources.get_episodes_for_calendar_week", return_value=[])
def test_npr_source_empty_week(mock_get_episodes):
    source = NprIndicatorSource()
    result = source.collect()

    assert result.has_content is False


@patch("jobs.sources.fetch_transcript")
@patch("jobs.sources.get_episodes_for_calendar_week")
def test_npr_source_retries_then_includes_late_friday_transcript(
    mock_get_episodes, mock_fetch
):
    friday = _episode(
        "EV sales slow, US Treasury yields grow",
        slug="friday",
    )
    thursday = _episode("Is bankruptcy really all that bad?", slug="thursday")
    mock_get_episodes.return_value = [thursday, friday]
    mock_fetch.side_effect = [
        "Thursday transcript.",
        None,
        "Friday transcript.",
    ]
    sleeps: list[float] = []

    source = NprIndicatorSource(retry_attempts=3, retry_delay_seconds=20, sleep=sleeps.append)
    result = source.collect()

    assert result.has_content is True
    assert "Thursday transcript." in result.prompt_text
    assert "Friday transcript." in result.prompt_text
    assert "EPISODE: EV sales slow" in result.prompt_text
    assert sleeps == [20]
    assert mock_fetch.call_count == 3


@patch("jobs.sources.fetch_transcript")
@patch("jobs.sources.get_episodes_for_calendar_week")
def test_npr_source_skips_unpublished_episode_and_keeps_the_rest(
    mock_get_episodes, mock_fetch
):
    mock_get_episodes.return_value = [
        _episode("Monday show", slug="mon"),
        _episode("Friday indicators", slug="fri"),
    ]
    mock_fetch.side_effect = lambda url: (
        "Monday transcript." if url.endswith("/mon") else None
    )
    sleeps: list[float] = []

    source = NprIndicatorSource(retry_attempts=3, retry_delay_seconds=5, sleep=sleeps.append)
    result = source.collect()

    assert result.has_content is True
    assert "Monday transcript." in result.prompt_text
    assert "EPISODE: Monday show" in result.prompt_text
    assert "Friday indicators" not in result.prompt_text
    assert sleeps == [5, 5]
    assert mock_fetch.call_count == 4


@patch("jobs.sources.fetch_transcript", return_value="Transcript text.")
@patch("jobs.sources.get_episodes_for_calendar_week")
def test_npr_source_accepts_short_holiday_week(mock_get_episodes, mock_fetch):
    mock_get_episodes.return_value = [
        _episode("Monday", slug="mon"),
        _episode("Tuesday", slug="tue"),
        _episode("Wednesday", slug="wed"),
        _episode("Thursday", slug="thu"),
    ]

    source = NprIndicatorSource(retry_attempts=1)
    result = source.collect()

    assert result.has_content is True
    assert result.prompt_text.count("EPISODE:") == 4
    assert mock_fetch.call_count == 4


@patch("jobs.sources.fetch_transcript", return_value=None)
@patch("jobs.sources.get_episodes_for_calendar_week")
def test_npr_source_empty_when_no_transcripts_ready(mock_get_episodes, mock_fetch):
    mock_get_episodes.return_value = [_episode("Friday indicators", slug="fri")]

    source = NprIndicatorSource(retry_attempts=2, retry_delay_seconds=1, sleep=lambda _: None)
    result = source.collect()

    assert result.has_content is False


def test_save_npr_summary_writes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save_npr_summary("# NPR Indicator Weekly Summary - June 25, 2026\n\nBody.")
    files = list((tmp_path / "summaries").glob("*.md"))
    assert len(files) == 1
    assert "Body." in files[0].read_text(encoding="utf-8")

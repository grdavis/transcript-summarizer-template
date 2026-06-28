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


@patch("jobs.sources.fetch_transcript", return_value="Transcript text.")
@patch("jobs.sources.get_episodes_for_calendar_week")
def test_npr_source_collects_transcripts(mock_get_episodes, mock_fetch):
    mock_get_episodes.return_value = [
        {
            "title": "Jobs report",
            "published": "2026-06-25",
            "transcript_url": "https://example.com/transcript",
        }
    ]

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


def test_save_npr_summary_writes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save_npr_summary("# NPR Indicator Weekly Summary - June 25, 2026\n\nBody.")
    files = list((tmp_path / "summaries").glob("*.md"))
    assert len(files) == 1
    assert "Body." in files[0].read_text(encoding="utf-8")

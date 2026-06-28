"""End-to-end tests for job runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import MagicMock, patch

from zoneinfo import ZoneInfo

from jobs.base import Job, SourceResult, run_job

TZ = ZoneInfo("America/Los_Angeles")


@dataclass
class FakeSource:
    result: SourceResult

    def collect(self) -> SourceResult:
        return self.result


def _job_with_source(result: SourceResult) -> Job:
    return Job(
        key="test",
        display_name="Test",
        group="daily",
        subject_prefix="Test Briefing",
        intro_template="Intro <strong>{date}</strong>.",
        prompt="Summarize this.",
        build_source=lambda: FakeSource(result),
    )


@patch("jobs.base.GmailClient")
@patch("jobs.base.generate_content", return_value="## Briefing\n\nSummary text.")
@patch("jobs.base.send_email")
def test_run_job_happy_path(mock_send, mock_generate, mock_client_cls):
    deliver_client = MagicMock()
    mock_client_cls.return_value = deliver_client
    on_success = MagicMock()
    job = _job_with_source(
        SourceResult(
            prompt_text="Source text here.",
            has_content=True,
            on_success=on_success,
        )
    )

    produced = run_job(job, dry_run=False)

    assert produced is True
    mock_generate.assert_called_once()
    mock_send.assert_called_once()
    deliver_client.connect.assert_called_once()
    deliver_client.disconnect.assert_called_once()
    on_success.assert_called_once_with("## Briefing\n\nSummary text.")


@patch("jobs.base.generate_content")
@patch("jobs.base.send_email")
def test_run_job_empty_day_skips(mock_send, mock_generate):
    job = _job_with_source(SourceResult(prompt_text="", has_content=False))

    produced = run_job(job, dry_run=False)

    assert produced is False
    mock_generate.assert_not_called()
    mock_send.assert_not_called()


@patch("jobs.base.generate_content", return_value="## Briefing\n\nSummary text.")
@patch("jobs.base.send_email")
def test_run_job_dry_run_does_not_send(mock_send, mock_generate):
    on_success = MagicMock()
    job = _job_with_source(
        SourceResult(
            prompt_text="Source text here.",
            has_content=True,
            dry_run_summary="Would mark 1 email(s) as read.",
            on_success=on_success,
        )
    )

    produced = run_job(job, dry_run=True)

    assert produced is True
    mock_generate.assert_called_once()
    mock_send.assert_not_called()
    on_success.assert_not_called()


@patch("jobs.base.GmailClient")
@patch("jobs.base.generate_content", return_value="Summary only.")
@patch("jobs.base.send_email")
def test_run_job_applies_markdown_prefix(mock_send, _mock_generate, _mock_client_cls):
    job = Job(
        key="test",
        display_name="Test",
        group="weekly",
        subject_prefix="Weekly Summary",
        intro_template="Intro <strong>{date}</strong>.",
        prompt="Summarize.",
        markdown_prefix="# Weekly Summary - {date}\n\n",
        build_source=lambda: FakeSource(
            SourceResult(prompt_text="Transcripts.", has_content=True)
        ),
    )

    run_job(job, dry_run=True)

    mock_send.assert_not_called()


@patch("jobs.base.GmailClient")
@patch("jobs.base.generate_content", return_value="Body text.")
@patch("jobs.base.send_email")
def test_run_job_markdown_prefix_in_live_run(mock_send, _mock_generate, mock_client_cls):
    job = Job(
        key="test",
        display_name="Test",
        group="weekly",
        subject_prefix="Weekly Summary",
        intro_template="Intro <strong>{date}</strong>.",
        prompt="Summarize.",
        markdown_prefix="# Weekly Summary - {date}\n\n",
        build_source=lambda: FakeSource(
            SourceResult(prompt_text="Transcripts.", has_content=True)
        ),
    )
    mock_client_cls.return_value = MagicMock()

    run_job(job, dry_run=False)

    markdown_body = mock_send.call_args.kwargs["markdown_body"]
    assert markdown_body.startswith("# Weekly Summary - ")
    assert markdown_body.endswith("Body text.")

"""Source implementations for collecting text to summarize."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Callable

from gmail_client import EmailMessage, GmailClient
from jobs.base import SourceResult
from scraper import fetch_transcript, get_episodes_for_calendar_week

# Friday's Indicator episode is often in the RSS feed before NPR publishes
# the transcript page. Retry missing fetches instead of silently dropping them.
NPR_TRANSCRIPT_RETRY_ATTEMPTS = 4
NPR_TRANSCRIPT_RETRY_DELAY_SECONDS = 20.0


def format_newsletters_for_prompt(emails: list[EmailMessage]) -> str:
    blocks: list[str] = []
    for msg in emails:
        blocks.append(
            "\n".join(
                [
                    "=" * 50,
                    f"FROM: {msg.sender}",
                    f"SUBJECT: {msg.subject}",
                    f"RECEIVED: {msg.received_at.isoformat()}",
                    "=" * 50,
                    "",
                    msg.body,
                ]
            )
        )
    return "\n\n".join(blocks)


IncludeFilter = Callable[[EmailMessage], bool]


class GmailSource:
    """Fetch and filter inbox messages from allowlisted senders."""

    def __init__(
        self,
        *,
        senders: list[str],
        lookback_hours: int | None = None,
        include_filter: IncludeFilter | None = None,
    ):
        self.senders = senders
        self.lookback_hours = lookback_hours
        self.include_filter = include_filter
        self._included: list[EmailMessage] = []

    def collect(self) -> SourceResult:
        client = GmailClient()
        client.connect()
        try:
            emails = client.fetch_from_senders(self.senders, self.lookback_hours)
            included = [
                msg
                for msg in emails
                if self.include_filter is None or self.include_filter(msg)
            ]
        finally:
            client.disconnect()

        self._included = included
        if not included:
            return SourceResult(prompt_text="", has_content=False)

        prompt_text = (
            "Here are the newsletters to synthesize:\n\n"
            f"{format_newsletters_for_prompt(included)}"
        )
        dry_run_summary = (
            f"Would mark {len(included)} email(s) as read: "
            f"{[m.uid for m in included]}"
        )
        return SourceResult(
            prompt_text=prompt_text,
            has_content=True,
            dry_run_summary=dry_run_summary,
            on_success=lambda _markdown: self._mark_included_as_read(),
        )

    def _mark_included_as_read(self) -> None:
        if not self._included:
            return
        client = GmailClient()
        client.connect()
        try:
            client.mark_as_read([msg.uid for msg in self._included])
        finally:
            client.disconnect()
        print(f"Marked {len(self._included)} source email(s) as read.")


def _save_npr_summary(markdown_body: str) -> None:
    os.makedirs("summaries", exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"summaries/{date_str}-indicator-summary.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown_body)
    print(f"Summary saved to {filename}")


class NprIndicatorSource:
    """Fetch NPR Indicator transcripts for the current calendar week."""

    def __init__(
        self,
        *,
        retry_attempts: int = NPR_TRANSCRIPT_RETRY_ATTEMPTS,
        retry_delay_seconds: float = NPR_TRANSCRIPT_RETRY_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.retry_attempts = retry_attempts
        self.retry_delay_seconds = retry_delay_seconds
        self._sleep = sleep

    def collect(self) -> SourceResult:
        episodes = get_episodes_for_calendar_week()
        if not episodes:
            return SourceResult(prompt_text="", has_content=False)

        transcripts = self._fetch_all_transcripts(episodes)
        included = [ep for ep in episodes if ep["transcript_url"] in transcripts]
        if not included:
            return SourceResult(prompt_text="", has_content=False)

        combined_text = ""
        for ep in included:
            combined_text += (
                f"\n\n{'=' * 50}\n"
                f"EPISODE: {ep['title']}\n"
                f"PUBLISHED: {ep['published']}\n"
                f"{'=' * 50}\n\n"
            )
            combined_text += transcripts[ep["transcript_url"]]

        print(f"Extracted {len(combined_text)} characters of transcript data.")
        date_str = datetime.now().strftime("%Y-%m-%d")
        prompt_text = (
            f"Here are the transcripts from {len(included)} episode(s):\n\n{combined_text}"
        )
        return SourceResult(
            prompt_text=prompt_text,
            has_content=True,
            dry_run_summary=f"Would save summary to summaries/{date_str}-indicator-summary.md",
            on_success=_save_npr_summary,
        )

    def _fetch_all_transcripts(self, episodes: list[dict]) -> dict[str, str]:
        """Fetch every episode transcript, retrying ones that are not published yet."""
        transcripts: dict[str, str] = {}
        pending = list(episodes)

        for attempt in range(1, self.retry_attempts + 1):
            still_pending: list[dict] = []
            for idx, ep in enumerate(pending, 1):
                label = f"[{idx}/{len(pending)}]"
                if attempt > 1:
                    label += f" retry {attempt}/{self.retry_attempts}"
                print(f"{label} Fetching transcript for: {ep['title']}")
                transcript = fetch_transcript(ep["transcript_url"])
                if transcript:
                    transcripts[ep["transcript_url"]] = transcript
                else:
                    print(f"  -> Transcript not ready for {ep['title']}")
                    still_pending.append(ep)

            pending = still_pending
            if not pending:
                return transcripts
            if attempt < self.retry_attempts:
                print(
                    f"Waiting {self.retry_delay_seconds:.0f}s for "
                    f"{len(pending)} unpublished transcript(s)..."
                )
                self._sleep(self.retry_delay_seconds)

        titles = ", ".join(ep["title"] for ep in pending)
        print(
            f"Skipping {len(pending)} episode(s) without a transcript: {titles}. "
            "Continuing with the rest of the week."
        )
        return transcripts

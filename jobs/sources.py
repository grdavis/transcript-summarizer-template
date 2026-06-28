"""Source implementations for collecting text to summarize."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Callable

from gmail_client import EmailMessage, GmailClient
from jobs.base import SourceResult
from scraper import fetch_transcript, get_episodes_for_calendar_week


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

    def collect(self) -> SourceResult:
        episodes = get_episodes_for_calendar_week()
        if not episodes:
            return SourceResult(prompt_text="", has_content=False)

        combined_text = ""
        fetched = 0
        for idx, ep in enumerate(episodes, 1):
            print(f"[{idx}/{len(episodes)}] Fetching transcript for: {ep['title']}")
            transcript = fetch_transcript(ep["transcript_url"])
            if transcript:
                fetched += 1
                combined_text += (
                    f"\n\n{'=' * 50}\n"
                    f"EPISODE: {ep['title']}\n"
                    f"PUBLISHED: {ep['published']}\n"
                    f"{'=' * 50}\n\n"
                )
                combined_text += transcript
            else:
                print(f"  -> Failed to fetch transcript for {ep['title']}")

        if not combined_text.strip():
            return SourceResult(prompt_text="", has_content=False)

        print(f"Extracted {len(combined_text)} characters of transcript data.")
        date_str = datetime.now().strftime("%Y-%m-%d")
        prompt_text = (
            f"Here are the transcripts from {fetched} episode(s):\n\n{combined_text}"
        )
        return SourceResult(
            prompt_text=prompt_text,
            has_content=True,
            dry_run_summary=f"Would save summary to summaries/{date_str}-indicator-summary.md",
            on_success=_save_npr_summary,
        )

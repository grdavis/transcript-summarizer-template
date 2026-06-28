"""Job definitions and runner for text -> LLM -> email pipelines."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from email_delivery import send_email
from gmail_client import GmailClient
from summarizer import generate_content

TZ = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True)
class SourceResult:
    """Collected text and optional post-delivery hook."""

    prompt_text: str
    has_content: bool
    dry_run_summary: str = ""
    on_success: Callable[[str], None] | None = None


class Source(Protocol):
    def collect(self) -> SourceResult:
        """Gather source text for the LLM prompt."""


@dataclass(frozen=True)
class Job:
    key: str
    display_name: str
    group: str
    subject_prefix: str
    intro_template: str
    prompt: str
    build_source: Callable[[], Source]
    markdown_prefix: str | None = None
    enabled: bool = True


def format_date_display(now: datetime) -> str:
    return (
        now.strftime("%B %-d, %Y")
        if sys.platform != "win32"
        else now.strftime("%B %d, %Y").replace(" 0", " ")
    )


def validate_registry(registry: list[Job]) -> None:
    """Ensure registry entries are well-formed."""
    keys = [job.key for job in registry]
    if len(keys) != len(set(keys)):
        raise ValueError("Job registry contains duplicate keys")

    for job in registry:
        if not job.key.strip():
            raise ValueError("Job key must be non-empty")
        if job.group not in {"daily", "weekly"}:
            raise ValueError(f"Job {job.key!r} has invalid group {job.group!r}")
        if not job.prompt.strip():
            raise ValueError(f"Job {job.key!r} has empty prompt")
        if not job.subject_prefix.strip():
            raise ValueError(f"Job {job.key!r} has empty subject_prefix")
        if not job.intro_template.strip():
            raise ValueError(f"Job {job.key!r} has empty intro_template")


def run_job(job: Job, *, dry_run: bool = False) -> bool:
    """Run one job. Returns True when output was produced."""
    if not job.enabled:
        print(f"[{job.key}] Disabled; skipping.")
        return False

    print(f"[{job.key}] Collecting source text...")
    source = job.build_source()
    result = source.collect()

    if not result.has_content:
        print(f"[{job.key}] No qualifying content; skipping.")
        return False

    print(f"[{job.key}] Summarizing...")
    full_prompt = f"{job.prompt}\n\n{result.prompt_text}"
    summary = generate_content(full_prompt, label=f"Gemini {job.key}")

    now = datetime.now(TZ)
    date_display = format_date_display(now)
    subject = f"{job.subject_prefix} - {date_display}"

    if job.markdown_prefix:
        markdown_body = job.markdown_prefix.replace("{date}", date_display) + summary
    else:
        markdown_body = summary

    if dry_run:
        print(f"\n--- DRY RUN: {job.key} ---")
        print(f"Subject: {subject}")
        if result.dry_run_summary:
            print(result.dry_run_summary)
        print(markdown_body)
        print(f"--- END DRY RUN: {job.key} ---\n")
        return True

    deliver_client = GmailClient()
    deliver_client.connect()
    try:
        send_email(
            subject=subject,
            markdown_body=markdown_body,
            date_str=date_display,
            intro_template=job.intro_template,
            gmail_client=deliver_client,
        )
        if result.on_success is not None:
            result.on_success(markdown_body)
    finally:
        deliver_client.disconnect()

    return True

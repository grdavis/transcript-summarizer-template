"""Build per-day briefing inputs from the same Gmail allowlist as the live job.

Messages are only read. Nothing is marked seen and nothing is sent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gmail_client import EmailMessage
from jobs.base import TZ
from jobs.sources import GmailSource, format_newsletters_for_prompt


@dataclass(frozen=True)
class DailyFixture:
    id: str
    prompt_text: str
    manifest: list[dict] = field(default_factory=list)


def group_messages(
    messages: list[EmailMessage],
    *,
    max_days: int,
    include_filter=None,
) -> list[DailyFixture]:
    """Group allowlisted mail by Pacific date and keep the most recent days."""
    if max_days < 1:
        raise ValueError(f"max_days must be positive, got {max_days}")

    included = [
        message
        for message in messages
        if include_filter is None or include_filter(message)
    ]
    by_day: dict[str, list[EmailMessage]] = {}
    for message in included:
        received = message.received_at
        if received.tzinfo is None:
            received = received.replace(tzinfo=TZ)
        else:
            received = received.astimezone(TZ)
        by_day.setdefault(received.date().isoformat(), []).append(message)

    fixtures: list[DailyFixture] = []
    for day in sorted(by_day)[-max_days:]:
        day_messages = sorted(by_day[day], key=lambda message: message.received_at)
        fixtures.append(
            DailyFixture(
                id=day,
                prompt_text=(
                    "Here are the newsletters to synthesize:\n\n"
                    f"{format_newsletters_for_prompt(day_messages)}"
                ),
                manifest=[
                    {
                        "sender": message.sender,
                        "subject": message.subject,
                        "chars": len(message.body),
                    }
                    for message in day_messages
                ],
            )
        )
    return fixtures


def load_gmail_fixtures(
    source: GmailSource,
    *,
    lookback_hours: int,
    max_days: int,
) -> list[DailyFixture]:
    """Fetch inbox mail the way the job does, without the mark-as-read hook."""
    from gmail_client import GmailClient

    client = GmailClient()
    client.connect()
    try:
        messages = client.fetch_from_senders(
            source.senders,
            lookback_hours,
            peek=True,
        )
    finally:
        client.disconnect()
    return group_messages(
        messages,
        max_days=max_days,
        include_filter=source.include_filter,
    )

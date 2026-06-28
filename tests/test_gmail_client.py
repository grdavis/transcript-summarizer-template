"""Tests for gmail_client helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from email import message_from_bytes
from pathlib import Path

from zoneinfo import ZoneInfo

from gmail_client import (
    EmailMessage,
    extract_body,
    imap_since_date,
    lookback_cutoff,
    parse_raw_message,
    within_lookback,
)

FIXTURES = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("America/Los_Angeles")


def _load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_extract_body_plain():
    msg = message_from_bytes(_load_fixture("plain.eml"))
    body = extract_body(msg)
    assert "plain text newsletter body" in body.lower()


def test_extract_body_html():
    msg = message_from_bytes(_load_fixture("html.eml"))
    body = extract_body(msg)
    assert "HTML body text" in body
    assert "<h1>" not in body


def test_extract_body_multipart_prefers_plain():
    msg = message_from_bytes(_load_fixture("multipart.eml"))
    body = extract_body(msg)
    assert "Plain part should win" in body


def test_parse_raw_message():
    parsed = parse_raw_message("42", _load_fixture("plain.eml"))
    assert parsed is not None
    assert parsed.uid == "42"
    assert "newsletter@example.com" in parsed.sender
    assert parsed.subject == "Plain text newsletter"


def test_within_lookback_boundary():
    now = datetime(2026, 6, 25, 8, 15, tzinfo=TZ)
    cutoff = lookback_cutoff(now, 24)
    assert within_lookback(cutoff, cutoff)
    assert within_lookback(cutoff + timedelta(hours=1), cutoff)
    assert not within_lookback(cutoff - timedelta(seconds=1), cutoff)


def test_imap_since_date_format():
    dt = datetime(2026, 6, 25, 8, 15, tzinfo=TZ)
    assert imap_since_date(dt) == "25-Jun-2026"


def test_email_message_frozen():
    msg = EmailMessage(
        uid="1",
        sender="a@b.com",
        subject="Hi",
        received_at=datetime.now(TZ),
        body="body",
    )
    assert msg.uid == "1"

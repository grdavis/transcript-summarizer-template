"""Tests for Pacific-time scheduling guard."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from wait_until_pacific import decide

TZ = ZoneInfo("America/Los_Angeles")


def test_decide_sleep_before_target():
    now = datetime(2026, 6, 28, 7, 30, tzinfo=TZ)
    assert decide(now, hour=8, minute=15, grace_minutes=90) == "sleep"


def test_decide_proceed_within_grace():
    now = datetime(2026, 6, 28, 9, 0, tzinfo=TZ)
    assert decide(now, hour=8, minute=15, grace_minutes=90) == "proceed"


def test_decide_skip_after_grace():
    now = datetime(2026, 6, 28, 10, 30, tzinfo=TZ)
    assert decide(now, hour=8, minute=15, grace_minutes=90) == "skip"


def test_decide_proceed_at_target():
    now = datetime(2026, 1, 15, 8, 15, tzinfo=TZ)
    assert decide(now, hour=8, minute=15, grace_minutes=90) == "proceed"

"""Tests for NPR week selection."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scraper import TZ, _iso_week_bounds


def test_saturday_reference_still_includes_friday():
    """A Saturday-morning job must stay in the same Mon–Sun week as Friday."""
    saturday = datetime(2026, 8, 22, 8, 0, tzinfo=TZ)
    week_lo, week_hi = _iso_week_bounds(saturday)

    friday_ep = datetime(2026, 8, 21, 3, 0, tzinfo=TZ)
    next_monday = datetime(2026, 8, 24, 3, 0, tzinfo=TZ)

    assert week_lo.date().isoformat() == "2026-08-17"
    assert week_hi.date().isoformat() == "2026-08-23"
    assert week_lo <= friday_ep <= week_hi
    assert not (week_lo <= next_monday <= week_hi)


def test_week_bounds_use_eastern_calendar():
    ref = datetime(2026, 8, 21, 18, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    week_lo, week_hi = _iso_week_bounds(ref.astimezone(TZ))
    assert week_lo.tzinfo == TZ
    assert week_lo.weekday() == 0
    assert week_hi.weekday() == 6

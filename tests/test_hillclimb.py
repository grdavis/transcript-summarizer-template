"""Tests for the briefing hill-climb scorer and fixture grouping."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from gmail_client import EmailMessage
from eval.candidates import EXTRA_CANDIDATES, Candidate, candidates_for
from eval.fixtures import group_messages
from eval.grader import length_score, parse_grade, total_score
from eval.hillclimb import (
    Trial,
    choose_winner,
    render_report,
)
from eval.hillclimb import RunResult
from briefing_length import listen_minutes, word_count
from jobs import REGISTRY

TZ = ZoneInfo("America/Los_Angeles")


def _message(uid: str, day: str, subject: str) -> EmailMessage:
    return EmailMessage(
        uid=uid,
        sender="Example Newsletter <newsletter@example.com>",
        subject=subject,
        received_at=datetime.fromisoformat(f"{day}T08:00:00-07:00"),
        body=f"Body for {subject}. " * 30,
    )


def test_group_messages_keeps_most_recent_days_in_pacific_time():
    messages = [
        _message("1", "2026-09-28", "Monday"),
        _message("2", "2026-09-29", "Tuesday"),
        _message("3", "2026-09-30", "Wednesday"),
        _message("4", "2026-09-27", "Sunday"),
    ]
    fixtures = group_messages(messages, max_days=2)
    assert [fixture.id for fixture in fixtures] == ["2026-09-29", "2026-09-30"]
    assert "Tuesday" in fixtures[0].prompt_text
    assert fixtures[0].manifest[0]["subject"] == "Tuesday"


def test_length_score_uses_the_requested_band():
    assert length_score(1200, minimum=1100, maximum=1400) == 5
    assert length_score(1000, minimum=1100, maximum=1400) == 3
    assert length_score(2000, minimum=1100, maximum=1400) == 1


def test_parse_grade_accepts_fenced_json():
    grade = parse_grade(
        '```json\n{"reader": 4, "listener": 5, "notes": "Keeps the argument."}\n```',
        grader_model="gemini-3.1-pro-preview",
    )
    assert grade.reader == 4
    assert grade.listener == 5
    assert total_score(grade) == 9
    assert total_score(grade, length=5) == 14


def test_choose_winner_requires_every_day_and_breaks_ties_toward_shorter():
    long = [
        Trial("long", "m", "d1", words=1600, length=2, reader=5, listener=5, total=14),
        Trial("long", "m", "d2", words=1600, length=2, reader=5, listener=5, total=14),
    ]
    tight = [
        Trial("tight", "m", "d1", words=1100, length=5, reader=4, listener=4, total=18),
        Trial("tight", "m", "d2", words=1100, length=5, reader=4, listener=4, total=18),
    ]
    broken = [
        Trial("broken", "m", "d1", words=1100, length=5, reader=5, listener=5, total=20),
        Trial("broken", "m", "d2", error="boom"),
    ]
    assert choose_winner(long + tight + broken) == "tight"


def test_candidates_follow_the_live_prompt_and_model_list(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "model-a,model-b")
    job = next(item for item in REGISTRY if item.key == "newsletter_example")
    found = candidates_for(job)
    assert [candidate.model for candidate in found] == ["model-a", "model-b"]
    assert all(candidate.prompt == job.prompt for candidate in found)
    assert EXTRA_CANDIDATES == {}


def test_word_count_and_listen_estimate():
    text = "one two three four five"
    assert word_count(text) == 5
    assert listen_minutes(225) == 1


def test_report_names_the_winner():
    result = RunResult(job="newsletter_example", winner="shorter")
    candidates = [Candidate("shorter", "Write tighter.", "gemini-flash-latest")]
    report = render_report(result, candidates)
    assert "Winner: `shorter`" in report
    assert "gemini-flash-latest" in report
    assert "Word target: none." in report

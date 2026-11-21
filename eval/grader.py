"""Independent grader for newsletter briefings.

The rubric is the standing preference for these briefings: attributed
arguments for the reader, and something a person can follow by ear. Length is
scored in code only when the hill climb was given a word target. The grader
model is a different alias from the Flash model that writes the briefing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

GRADER_MODELS = ["gemini-pro-latest", "gemini-flash-lite-latest"]

GRADE_PROMPT = """You are grading a newsletter briefing for two readers. Do not grade length.

Reader 1, the primary reader: they do not read the sources. They want the nuance, the argument, and any disagreement, with opinions attributed to the person or publication that made them. A neutral headline list is a failure even if it is accurate. One sharp insight is worth more than covering every item. Fluff, repeated setup, and a sign-off should score lower.

Reader 2, a normal listener: they hear this once, quickly. They should leave knowing what happened and why an informed person cares. Penalize stacked clauses, jargon with no explanation, and takes that have no reason behind them. Penalize claims the sources do not support.

Score each reader from 1 to 5 (5 is best). Reply with only this JSON object:
{{"reader": <int>, "listener": <int>, "notes": "<one or two sentences>"}}

SOURCES:
{sources}

BRIEFING:
{briefing}
"""


@dataclass(frozen=True)
class Grade:
    reader: int
    listener: int
    notes: str
    grader_model: str


def length_score(words: int, *, minimum: int, maximum: int) -> int:
    """5 inside the requested band. Falls off as the briefing leaves that band."""
    if minimum <= 0 or maximum < minimum:
        raise ValueError(f"need 0 < minimum <= maximum, got {minimum}, {maximum}")
    if words < 0:
        raise ValueError(f"words must be non-negative, got {words}")
    if minimum <= words <= maximum:
        return 5
    if words < minimum:
        gap = (minimum - words) / minimum
    else:
        gap = (words - maximum) / maximum
    if gap <= 0.15:
        return 3
    if gap <= 0.30:
        return 2
    return 1


def total_score(grade: Grade, length: int | None = None) -> int:
    if length is None:
        return grade.reader + grade.listener
    return grade.reader + grade.listener + length


def parse_grade(raw: str, *, grader_model: str) -> Grade:
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Grader did not return JSON: {raw[:200]!r}")
    payload = json.loads(match.group(0))
    reader = _score(payload.get("reader"), "reader")
    listener = _score(payload.get("listener"), "listener")
    notes = str(payload.get("notes") or "").strip()
    return Grade(reader=reader, listener=listener, notes=notes, grader_model=grader_model)


def _score(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Grader field {field} must be an integer, got {value!r}")
    score = int(value)
    if score < 1 or score > 5:
        raise ValueError(f"Grader field {field} must be 1-5, got {score}")
    return score

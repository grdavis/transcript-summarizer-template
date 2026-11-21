"""Word counts for newsletter briefings.

Listen-time estimates use a narration rate of 150 words per minute at 1.0x,
then the briefing playback tempo (default 1.5x).
"""

from __future__ import annotations

import re

NARRATION_WPM = 150
DEFAULT_PLAYBACK_TEMPO = 1.5


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", text))


def listen_minutes(words: int, *, tempo: float = DEFAULT_PLAYBACK_TEMPO) -> float:
    if words < 0:
        raise ValueError(f"words must be non-negative, got {words}")
    if tempo <= 0:
        raise ValueError(f"tempo must be positive, got {tempo}")
    return words / (NARRATION_WPM * tempo)

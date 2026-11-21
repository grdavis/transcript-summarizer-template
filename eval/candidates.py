"""Setups compared by `python -m eval.hillclimb`.

The live prompt is always included, once for each model in the production list
(`GEMINI_MODELS`, otherwise `DEFAULT_MODELS`). To try a different prompt, add
candidates for that job key and run the hill climb. Delete them after the
winner is copied into the job definition so the next request starts clean.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobs.base import Job
from summarizer import _get_models

# Fill this in for a single hill climb, then empty it again.
# Example:
# EXTRA_CANDIDATES = {
#     "newsletter_example": [
#         Candidate("shorter", prompt="...", model="gemini-flash-latest"),
#     ],
# }
EXTRA_CANDIDATES: dict[str, list[Candidate]] = {}

COMPRESS_PROMPT = """Rewrite the briefing below to at most {max_words} words.
Keep its structure, attributed opinions, and disagreements.
Do not add facts that are not already in the briefing.
Do not add a sign-off.

BRIEFING:
{summary}
"""


@dataclass(frozen=True)
class Candidate:
    """One prompt/model setup.

    When `compress_over` is set, a briefing longer than that many words is
    rewritten once with the same model.
    """

    key: str
    prompt: str
    model: str
    compress_over: int | None = None


def candidates_for(job: Job) -> list[Candidate]:
    """Live prompt on each production model, plus any extras for this job."""
    live = [
        Candidate(key=f"live-{model}", prompt=job.prompt, model=model)
        for model in _get_models()
    ]
    return live + list(EXTRA_CANDIDATES.get(job.key, []))

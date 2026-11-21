"""Compare briefing setups and let a separate grader pick one.

Usage:
    python -m eval.hillclimb --job newsletter_example --lookback-hours 96 --max-days 3

Results land in eval/results/<timestamp>/. Source newsletters are copied there
so the same inputs can be graded again; that directory is gitignored.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from briefing_length import listen_minutes, word_count
from eval.candidates import COMPRESS_PROMPT, Candidate, candidates_for
from eval.fixtures import DailyFixture, load_gmail_fixtures
from eval.grader import (
    GRADE_PROMPT,
    GRADER_MODELS,
    Grade,
    length_score,
    parse_grade,
    total_score,
)
from jobs import REGISTRY
from jobs.sources import GmailSource
from summarizer import generate_content

RESULTS_ROOT = Path("eval/results")
# One retry is enough to tell a 503 from a dead model without stalling the run.
EXPERIMENT_ATTEMPT_BUDGET = 2


@dataclass
class Trial:
    candidate: str
    model: str
    fixture: str
    words: int | None = None
    length: int | None = None
    reader: int | None = None
    listener: int | None = None
    total: int | None = None
    listen_minutes: float | None = None
    grader_model: str | None = None
    notes: str = ""
    error: str = ""
    compressed: bool = False
    summary_path: str = ""


@dataclass
class RunResult:
    job: str
    trials: list[Trial] = field(default_factory=list)
    winner: str = ""
    target_min_words: int | None = None
    target_max_words: int | None = None


def run_candidate(candidate: Candidate, fixture: DailyFixture) -> tuple[str, bool]:
    summary = generate_content(
        f"{candidate.prompt}\n\n{fixture.prompt_text}",
        label=f"{candidate.key} {fixture.id}",
        models=[candidate.model],
        attempt_budget=EXPERIMENT_ATTEMPT_BUDGET,
    )
    compressed = False
    if candidate.compress_over is not None and word_count(summary) > candidate.compress_over:
        summary = generate_content(
            COMPRESS_PROMPT.format(summary=summary, max_words=candidate.compress_over),
            label=f"{candidate.key} {fixture.id} compress",
            models=[candidate.model],
            attempt_budget=EXPERIMENT_ATTEMPT_BUDGET,
        )
        compressed = True
    return summary, compressed


def grade_summary(fixture: DailyFixture, summary: str) -> Grade:
    prompt = GRADE_PROMPT.format(sources=fixture.prompt_text, briefing=summary)
    last_error: BaseException | None = None
    for model in GRADER_MODELS:
        try:
            raw = generate_content(
                prompt,
                label=f"grader {model}",
                models=[model],
                attempt_budget=EXPERIMENT_ATTEMPT_BUDGET,
            )
            return parse_grade(raw, grader_model=model)
        except Exception as exc:
            last_error = exc
            print(f"Grader {model} failed: {exc}", file=sys.stderr)
    assert last_error is not None
    raise last_error


def score_trials(
    trials: list[Trial],
    *,
    target_min_words: int | None,
    target_max_words: int | None,
) -> None:
    """Fill listen estimates, and a length score when a word target was requested."""
    for trial in trials:
        if trial.words is None or trial.error:
            continue
        trial.listen_minutes = round(listen_minutes(trial.words), 2)
        if trial.reader is None or trial.listener is None:
            continue
        grade = Grade(trial.reader, trial.listener, trial.notes, trial.grader_model or "")
        if target_min_words is None or target_max_words is None:
            trial.total = total_score(grade)
            continue
        trial.length = length_score(
            trial.words,
            minimum=target_min_words,
            maximum=target_max_words,
        )
        trial.total = total_score(grade, length=trial.length)


def choose_winner(trials: list[Trial]) -> str:
    """Highest mean total.

    Prefer a setup that graded every day. If 503s or quota left nobody with a
    full set, take the best mean among setups with at least two graded days
    (or one day, when that is all the run collected).
    """
    fixture_count = len({trial.fixture for trial in trials})
    if fixture_count == 0:
        return ""
    minimums = [fixture_count]
    if fixture_count > 1:
        minimums.append(max(2, fixture_count - 1))
    minimums.append(1)

    by_candidate: dict[str, list[Trial]] = defaultdict(list)
    for trial in trials:
        by_candidate[trial.candidate].append(trial)

    for minimum in minimums:
        best_key = ""
        best_mean = -1.0
        best_reader = -1.0
        best_words = 10**9
        for key, group in by_candidate.items():
            graded = [trial for trial in group if not trial.error and trial.total is not None]
            if len(graded) < minimum:
                continue
            mean_total = sum(trial.total or 0 for trial in graded) / len(graded)
            mean_reader = sum(trial.reader or 0 for trial in graded) / len(graded)
            mean_words = sum(trial.words or 0 for trial in graded) / len(graded)
            if (mean_total, mean_reader, -mean_words) > (best_mean, best_reader, -best_words):
                best_key = key
                best_mean = mean_total
                best_reader = mean_reader
                best_words = mean_words
        if best_key:
            return best_key
    return ""


def render_report(result: RunResult, candidates: list[Candidate]) -> str:
    by_key = {candidate.key: candidate for candidate in candidates}
    target = "none"
    if result.target_min_words is not None and result.target_max_words is not None:
        target = f"{result.target_min_words}-{result.target_max_words} words"
    lines = [
        f"# Briefing hill climb ({result.job})",
        "",
        f"Word target: {target}.",
        "Listen minutes assume 150 spoken words per minute at 1.5x playback.",
        "",
        "| Setup | Model | Mean words | Listen min | Length | Reader | Listener | Total |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    grouped: dict[str, list[Trial]] = defaultdict(list)
    for trial in result.trials:
        grouped[trial.candidate].append(trial)

    for key, group in grouped.items():
        candidate = by_key.get(key)
        model = candidate.model if candidate else group[0].model
        ok = [trial for trial in group if not trial.error and trial.total is not None]
        if not ok:
            lines.append(f"| {key} | {model} |  |  |  |  |  | failed |")
            continue
        def avg(attr: str) -> float:
            return sum(getattr(trial, attr) or 0 for trial in ok) / len(ok)

        length = ""
        if any(trial.length is not None for trial in ok):
            length = f"{avg('length'):.1f}"
        lines.append(
            f"| {key} | {model} | {avg('words'):.0f} | {avg('listen_minutes'):.1f} | "
            f"{length} | {avg('reader'):.1f} | {avg('listener'):.1f} | {avg('total'):.1f} |"
        )

    lines.extend(["", f"Winner: `{result.winner or 'none'}`", ""])
    if result.winner and result.winner in by_key:
        winner = by_key[result.winner]
        lines.append("Winning setup:")
        lines.append(f"- model: `{winner.model}`")
        lines.append(f"- compress when over: {winner.compress_over or 'no'}")
        lines.append("")
        lines.append("```")
        lines.append(winner.prompt.strip())
        lines.append("```")
        lines.append("")

    lines.append("## Per day")
    lines.append("")
    for trial in result.trials:
        status = trial.error or (
            f"{trial.words} words, ~{trial.listen_minutes} min, "
            f"length {trial.length}, reader {trial.reader}, listener {trial.listener}, "
            f"total {trial.total}"
        )
        extra = " (compressed)" if trial.compressed else ""
        lines.append(f"- `{trial.fixture}` `{trial.candidate}`{extra}: {status}")
        if trial.notes:
            lines.append(f"  - {trial.notes}")
    lines.append("")
    return "\n".join(lines)


def write_results(
    result: RunResult,
    candidates: list[Candidate],
    fixtures: list[DailyFixture],
    summaries: dict[tuple[str, str], str],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir = output_dir / "fixtures"
    fixture_dir.mkdir(exist_ok=True)
    for fixture in fixtures:
        (fixture_dir / f"{fixture.id}.txt").write_text(fixture.prompt_text, encoding="utf-8")
        (fixture_dir / f"{fixture.id}.manifest.json").write_text(
            json.dumps(fixture.manifest, indent=2),
            encoding="utf-8",
        )
    summary_dir = output_dir / "summaries"
    summary_dir.mkdir(exist_ok=True)
    for (candidate_key, fixture_id), summary in summaries.items():
        path = summary_dir / f"{fixture_id}--{candidate_key}.md"
        path.write_text(summary, encoding="utf-8")

    payload = {
        "job": result.job,
        "target_min_words": result.target_min_words,
        "target_max_words": result.target_max_words,
        "winner": result.winner,
        "candidates": [
            {
                "key": candidate.key,
                "model": candidate.model,
                "compress_over": candidate.compress_over,
                "prompt": candidate.prompt,
            }
            for candidate in candidates
        ],
        "trials": [asdict(trial) for trial in result.trials],
    }
    (output_dir / "scores.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(result, candidates), encoding="utf-8")


def hillclimb(
    *,
    job_key: str,
    fixtures: list[DailyFixture],
    candidates: list[Candidate],
    target_min_words: int | None = None,
    target_max_words: int | None = None,
) -> tuple[RunResult, dict[tuple[str, str], str]]:
    if not fixtures:
        raise RuntimeError("No newsletter days to grade")

    trials: list[Trial] = []
    summaries: dict[tuple[str, str], str] = {}
    for fixture in fixtures:
        print(f"Fixture {fixture.id}: {len(fixture.manifest)} email(s)", flush=True)
        for candidate in candidates:
            trial = Trial(candidate=candidate.key, model=candidate.model, fixture=fixture.id)
            try:
                summary, compressed = run_candidate(candidate, fixture)
                trial.compressed = compressed
                trial.words = word_count(summary)
                summaries[(candidate.key, fixture.id)] = summary
                grade = grade_summary(fixture, summary)
                trial.reader = grade.reader
                trial.listener = grade.listener
                trial.notes = grade.notes
                trial.grader_model = grade.grader_model
                print(
                    f"  {candidate.key}: {trial.words} words "
                    f"(reader {grade.reader}, listener {grade.listener})",
                    flush=True,
                )
            except Exception as exc:
                trial.error = f"{type(exc).__name__}: {exc}"
                print(f"  {candidate.key} failed: {trial.error}", file=sys.stderr, flush=True)
                traceback.print_exc()
            trials.append(trial)

    score_trials(
        trials,
        target_min_words=target_min_words,
        target_max_words=target_max_words,
    )
    result = RunResult(
        job=job_key,
        trials=trials,
        winner=choose_winner(trials),
        target_min_words=target_min_words,
        target_max_words=target_max_words,
    )
    return result, summaries


def _job(job_key: str):
    job = next((item for item in REGISTRY if item.key == job_key), None)
    if job is None:
        known = ", ".join(item.key for item in REGISTRY)
        raise SystemExit(f"Unknown job {job_key!r}. Known jobs: {known}")
    return job


def _gmail_source(job) -> GmailSource:
    source = job.build_source()
    if not isinstance(source, GmailSource):
        raise SystemExit(f"Job {job.key!r} does not read Gmail; pass fixtures another way.")
    return source


def _word_target(minimum: int, maximum: int) -> tuple[int | None, int | None]:
    if minimum == 0 and maximum == 0:
        return None, None
    if minimum <= 0 or maximum < minimum:
        raise SystemExit(
            "--target-min-words and --target-max-words must both be set, "
            f"with 0 < min <= max (got {minimum}, {maximum})"
        )
    return minimum, maximum


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hill-climb a newsletter briefing setup.")
    parser.add_argument("--job", default="newsletter_example")
    parser.add_argument("--lookback-hours", type=int, default=96)
    parser.add_argument("--max-days", type=int, default=3)
    parser.add_argument("--target-min-words", type=int, default=0)
    parser.add_argument("--target-max-words", type=int, default=0)
    args = parser.parse_args(argv)
    target_min, target_max = _word_target(args.target_min_words, args.target_max_words)

    job = _job(args.job)
    fixtures = load_gmail_fixtures(
        _gmail_source(job),
        lookback_hours=args.lookback_hours,
        max_days=args.max_days,
    )
    if not fixtures:
        print("No qualifying newsletters in the lookback window.", file=sys.stderr)
        return 1

    candidates = candidates_for(job)
    result, summaries = hillclimb(
        job_key=args.job,
        fixtures=fixtures,
        candidates=candidates,
        target_min_words=target_min,
        target_max_words=target_max,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = RESULTS_ROOT / stamp
    write_results(result, candidates, fixtures, summaries, output_dir)
    print(render_report(result, candidates))
    print(f"Wrote {output_dir}")
    return 0 if result.winner else 1


if __name__ == "__main__":
    raise SystemExit(main())

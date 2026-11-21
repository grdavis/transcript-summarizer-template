#!/usr/bin/env python3
"""Run text -> LLM -> email pipeline jobs from the registry."""

from __future__ import annotations

import argparse
import sys
import time
import traceback

from dotenv import load_dotenv

from jobs import REGISTRY, Job
from jobs.base import run_job

load_dotenv()

RETRY_PAUSE_SECONDS = 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run text -> LLM -> email pipeline jobs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and summarize without sending email or running post-delivery hooks.",
    )
    parser.add_argument(
        "--only",
        metavar="KEY",
        help="Run a single job by key (e.g. newsletter_example, npr_indicator).",
    )
    parser.add_argument(
        "--group",
        choices=["daily", "weekly"],
        help="Run all jobs in a schedule group.",
    )
    return parser.parse_args()


def selected_jobs(*, only: str | None, group: str | None) -> list[Job]:
    if only:
        matches = [job for job in REGISTRY if job.key == only]
        if not matches:
            keys = ", ".join(job.key for job in REGISTRY)
            raise SystemExit(f"Unknown job {only!r}. Available: {keys}")
        return matches

    if group:
        matches = [job for job in REGISTRY if job.group == group]
        if not matches:
            raise SystemExit(f"No jobs found for group {group!r}.")
        return matches

    return REGISTRY


def _run_jobs(jobs: list[Job], *, dry_run: bool) -> list[Job]:
    """Run jobs once. Returns the list of jobs that raised."""
    failed: list[Job] = []
    for job in jobs:
        try:
            run_job(job, dry_run=dry_run)
        except Exception as exc:
            failed.append(job)
            print(f"[{job.key}] Failed: {exc}", file=sys.stderr)
            traceback.print_exc()
    return failed


def main() -> None:
    args = parse_args()
    jobs = selected_jobs(only=args.only, group=args.group)

    failed = _run_jobs(jobs, dry_run=args.dry_run)

    if failed and not args.dry_run:
        keys = ", ".join(job.key for job in failed)
        print(
            f"\nRetrying {len(failed)} failed job(s) ({keys}) "
            f"after {RETRY_PAUSE_SECONDS}s pause...",
            file=sys.stderr,
        )
        time.sleep(RETRY_PAUSE_SECONDS)
        failed = _run_jobs(failed, dry_run=False)

    if failed:
        keys = ", ".join(job.key for job in failed)
        print(f"Failed jobs after retry: {keys}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

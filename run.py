#!/usr/bin/env python3
"""Run text -> LLM -> email pipeline jobs from the registry."""

from __future__ import annotations

import argparse
import sys
import traceback

from dotenv import load_dotenv

from jobs import REGISTRY, Job
from jobs.base import run_job

load_dotenv()


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


def main() -> None:
    args = parse_args()
    jobs = selected_jobs(only=args.only, group=args.group)

    failures = 0
    for job in jobs:
        try:
            run_job(job, dry_run=args.dry_run)
        except Exception as exc:
            failures += 1
            print(f"[{job.key}] Failed: {exc}", file=sys.stderr)
            traceback.print_exc()

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

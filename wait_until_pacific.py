#!/usr/bin/env python3
"""Wait until a target clock time in America/Los_Angeles (DST-aware)."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wait until a Pacific time today.")
    parser.add_argument("--hour", type=int, default=8)
    parser.add_argument("--minute", type=int, default=15)
    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=90,
        help="If already past target but within this window, proceed. Otherwise skip.",
    )
    return parser.parse_args()


def decide(now: datetime, *, hour: int, minute: int, grace_minutes: int) -> str:
    """Return 'sleep', 'proceed', or 'skip' for the given Pacific-local now."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < target:
        return "sleep"
    if now - target <= timedelta(minutes=grace_minutes):
        return "proceed"
    return "skip"


def main() -> None:
    args = parse_args()
    now = datetime.now(TZ)
    target = now.replace(hour=args.hour, minute=args.minute, second=0, microsecond=0)
    action = decide(
        now,
        hour=args.hour,
        minute=args.minute,
        grace_minutes=args.grace_minutes,
    )

    if action == "sleep":
        wait_seconds = (target - now).total_seconds()
        print(f"Now {now:%H:%M} PT; sleeping {wait_seconds:.0f}s until {target:%H:%M} PT")
        time.sleep(wait_seconds)
        return

    if action == "proceed":
        late_minutes = (now - target).total_seconds() / 60
        print(f"Now {now:%H:%M} PT; {late_minutes:.0f} min past target — proceeding")
        return

    late_minutes = (now - target).total_seconds() / 60
    print(f"Now {now:%H:%M} PT; too late ({late_minutes:.0f} min past target) — skipping")
    sys.exit(0)


if __name__ == "__main__":
    main()

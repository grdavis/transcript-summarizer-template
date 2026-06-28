import os
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

RSS_URL = "https://feeds.npr.org/510325/podcast.xml"
TZ = ZoneInfo("America/New_York")


def _entry_dt(entry):
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def _transcript_url(link: str) -> str | None:
    m = re.search(r"/(nx-s1-\d+)/", link) or re.search(r"/(\d+)/", link)
    return f"https://www.npr.org/transcripts/{m.group(1)}" if m else None


def _iso_week_bounds(ref_local: datetime) -> tuple[datetime, datetime]:
    monday = ref_local.date() - timedelta(days=ref_local.weekday())
    sunday = monday + timedelta(days=6)
    return (
        datetime.combine(monday, time.min, tzinfo=ref_local.tzinfo),
        datetime.combine(sunday, time.max, tzinfo=ref_local.tzinfo),
    )


def _reference_now() -> datetime:
    raw = (os.environ.get("SUMMARY_WEEK_REFERENCE") or "").strip()
    if not raw:
        return datetime.now(TZ)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(TZ)
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def get_episodes_for_calendar_week(max_feed_items: int = 40) -> list[dict]:
    """Episodes published Mon–Sun ISO week (US/Eastern) containing reference time; count varies."""
    ref = _reference_now().astimezone(TZ)
    week_lo, week_hi = _iso_week_bounds(ref)
    feed = feedparser.parse(RSS_URL)

    rows: list[tuple[datetime, dict]] = []
    for entry in feed.entries[:max_feed_items]:
        dt = _entry_dt(entry)
        if not dt:
            continue
        local = dt.astimezone(TZ)
        if local < week_lo or local > week_hi:
            continue
        url = _transcript_url(entry.link)
        if not url:
            continue
        rows.append(
            (
                local,
                {
                    "title": entry.title,
                    "published": entry.get("published") or entry.get("updated") or "",
                    "transcript_url": url,
                },
            )
        )

    rows.sort(key=lambda x: x[0])
    out, seen = [], set()
    for _, ep in rows:
        if ep["transcript_url"] not in seen:
            seen.add(ep["transcript_url"])
            out.append(ep)
    return out


def fetch_transcript(url: str) -> str | None:
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        return None
    div = BeautifulSoup(r.content, "html.parser").find("div", class_="transcript storytext")
    return div.get_text(strip=True, separator="\n") if div else None


if __name__ == "__main__":
    eps = get_episodes_for_calendar_week()
    print(f"Week digest: {len(eps)} episode(s)")
    for ep in eps:
        print(f"  - {ep['title']}\n    {ep['transcript_url']}")
        t = fetch_transcript(ep["transcript_url"])
        print(f"    ({len(t)} chars)\n" if t else "    (fetch failed)\n")

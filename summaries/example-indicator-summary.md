# NPR Indicator Weekly Summary - Example

This file is a **demo output** showing what the weekly NPR Indicator job produces. Your runs will write dated files here via `NprIndicatorSource.on_success`.

## Sample structure

A typical summary condenses multiple episode transcripts into one readable digest:

- **Monday** — Key economic stories and data points from the week's first episode.
- **Tuesday** — Follow-up themes or a deep dive on one topic.
- **Wednesday through Friday** — Additional episodes when published.

Each section preserves the main insights while removing ads, sponsor reads, and intro/outro filler.

## Customize the scraper

To adapt this pattern for another podcast or site, edit [`scraper.py`](scraper.py):

| Customize | Where |
|-----------|--------|
| RSS feed URL | `RSS_URL` |
| Transcript link extraction | `_transcript_url()` |
| HTML content selector | `fetch_transcript()` |
| Calendar week bounds | `get_episodes_for_calendar_week()` |

See the README for the full extension guide.

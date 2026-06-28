"""Built-in example job definitions.

Copy and adapt these jobs for your own sources, senders, and prompts.
"""

from __future__ import annotations

from jobs.base import Job
from jobs.sources import GmailSource, NprIndicatorSource

NEWSLETTER_EXAMPLE_PROMPT = """You are an expert editor summarizing newsletters for a busy reader.

Write a single briefing sized to the material (up to ~1,000 words; shorter is fine on a light day). Structure:

- A one-line date header.
- Top stories: lead with the biggest themes. Explain what happened and weave in the authors' analysis and opinions where present. Attribute opinions to their source.
- Also notable: shorter quick-hit bullets for other items, each 1-2 sentences.

Tone: substantive and opinion-preserving where the sources have a point of view. Do not flatten everything into neutral headlines. Use markdown headers (## / ###) for sections. Do NOT use em dashes; use hyphens or rephrase. Do NOT add a signature or sign-off."""

NPR_INDICATOR_PROMPT = """You are an expert editor and summarizer. Below are transcripts from NPR Indicator podcast episodes that aired during the same calendar week (weekday releases only; count may be fewer than five if there were holidays, feed gaps, or reruns).

Your task is to condense these transcripts into a single, cohesive summary transcript that is approximately 80% shorter than the combined original text. If there is only one episode, still produce a tight summary (same relative compression goal).

Requirements:
1. Keep the gist of all the topics and the most important insights.
2. Completely remove all advertisements, sponsor reads, and standard intro/outro fluff.
3. Structure the output clearly, perhaps by episode topic or day, but maintain a readable, engaging flow.
4. Ensure the final output is concise, punchy, and easy to read."""

JOBS: list[Job] = [
    Job(
        key="newsletter_example",
        display_name="Newsletter Example",
        group="daily",
        subject_prefix="Newsletter Briefing",
        prompt=NEWSLETTER_EXAMPLE_PROMPT,
        intro_template="Your newsletter briefing for <strong>{date}</strong> is below.",
        build_source=lambda: GmailSource(
            senders=[
                "newsletter@example.com",
            ],
        ),
    ),
    Job(
        key="npr_indicator",
        display_name="NPR Indicator",
        group="weekly",
        subject_prefix="NPR Indicator Weekly Summary",
        prompt=NPR_INDICATOR_PROMPT,
        intro_template=(
            "Your weekly NPR Indicator summary for <strong>{date}</strong> is below."
        ),
        markdown_prefix="# NPR Indicator Weekly Summary - {date}\n\n",
        build_source=lambda: NprIndicatorSource(),
    ),
]

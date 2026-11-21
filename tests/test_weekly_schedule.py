"""Tests for weekly NPR Indicator workflow trigger configuration."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/summarize.yml").read_text(encoding="utf-8")


def test_weekly_workflow_runs_saturday_not_friday():
    """Friday transcripts are often unpublished at a Friday-afternoon UTC run."""
    assert "cron: '0 15 * * 6'" in WORKFLOW
    assert "0 22 * * 5" not in WORKFLOW


def test_weekly_workflow_supports_manual_dispatch():
    assert "workflow_dispatch:" in WORKFLOW

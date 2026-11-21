"""Tests for daily briefing workflow trigger configuration."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/daily-briefing.yml").read_text(encoding="utf-8")


def test_workflow_has_no_github_schedule():
    assert "schedule:" not in WORKFLOW
    assert "cron:" not in WORKFLOW


def test_workflow_supports_manual_dispatch():
    assert "workflow_dispatch:" in WORKFLOW


def test_workflow_has_concurrency_group():
    assert "group: daily-briefing" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW

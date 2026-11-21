"""The hill climb is manual, so it never rides along with the morning briefing."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/eval-briefing.yml").read_text(encoding="utf-8")


def test_hillclimb_workflow_is_manual_only():
    assert "workflow_dispatch:" in WORKFLOW
    assert "schedule:" not in WORKFLOW
    assert "push:" not in WORKFLOW
    assert "pull_request:" not in WORKFLOW


def test_hillclimb_workflow_reads_mail_and_uploads_results():
    assert "python -m eval.hillclimb" in WORKFLOW
    assert "GMAIL_APP_PASSWORD" in WORKFLOW
    assert "upload-artifact" in WORKFLOW
    assert "eval/results/" in WORKFLOW
    assert "Set both word-target inputs, or leave both empty." in WORKFLOW

"""Tests for job registry."""

from __future__ import annotations

from jobs import REGISTRY, validate_registry


def test_validate_registry_passes():
    validate_registry(REGISTRY)


def test_registry_has_all_jobs():
    keys = {job.key for job in REGISTRY}
    assert keys == {
        "newsletter_example",
        "npr_indicator",
    }


def test_all_jobs_have_prompts_and_subjects():
    for job in REGISTRY:
        assert job.prompt.strip()
        assert job.subject_prefix.strip()
        assert job.intro_template.strip()

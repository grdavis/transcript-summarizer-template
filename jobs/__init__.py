"""Job registry for text -> LLM -> email pipelines."""

from __future__ import annotations

from jobs.base import Job, validate_registry
from jobs.definitions import JOBS

REGISTRY: list[Job] = [
    *JOBS,
]

validate_registry(REGISTRY)

__all__ = ["REGISTRY", "Job", "validate_registry"]

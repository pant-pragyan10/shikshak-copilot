"""Eval dataset models and loaders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RetrievalCase(BaseModel):
    """One retrieval eval case: a teacher's question + the source that should surface."""

    id: str
    question: str
    expected_source: str = Field(description="Filename of the curriculum chunk that should rank.")
    subject: str | None = None
    grade: str | None = None
    board: str | None = None
    note: str | None = None


def load_retrieval_cases(path: str | Path) -> list[RetrievalCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = data["cases"] if isinstance(data, dict) else data
    return [RetrievalCase.model_validate(c) for c in cases]


def load_grading_samples(path: str | Path) -> list[dict[str, Any]]:
    """Load the grading eval samples (the existing data/eval/grading_samples.json shape)."""
    samples: list[dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
    return samples

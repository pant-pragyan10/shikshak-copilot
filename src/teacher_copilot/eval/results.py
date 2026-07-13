"""Structured eval-result models and JSON persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_DEFAULT_RESULTS_DIR = Path("eval/results")


class EvalRun(BaseModel):
    """A single eval run's output — serialised to ``eval/results/``."""

    eval: str = Field(description="Which eval, e.g. 'retrieval' or 'grading'.")
    created_at: str = Field(description="UTC ISO timestamp.")
    judge: str = Field(
        default="deterministic",
        description="How results were judged (e.g. free-tier LLM model id, or 'deterministic').",
    )
    caveats: str = Field(default="", description="Honest limitations for reading these numbers.")
    summary: dict[str, Any] = Field(description="Headline metrics.")
    details: dict[str, Any] = Field(default_factory=dict, description="Per-case detail.")


def make_run(
    eval_name: str, *, summary: dict[str, Any], details: dict[str, Any], judge: str, caveats: str
) -> EvalRun:
    return EvalRun(
        eval=eval_name,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        judge=judge,
        caveats=caveats,
        summary=summary,
        details=details,
    )


def save_run(run: EvalRun, *, base_dir: str | Path = _DEFAULT_RESULTS_DIR) -> Path:
    """Write ``run`` to ``base_dir/{eval}_{timestamp}.json`` and return the path."""
    directory = Path(base_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = run.created_at.replace(":", "").replace("-", "").replace("+0000", "")
    path = directory / f"{run.eval}_{stamp}.json"
    path.write_text(json.dumps(run.model_dump(), indent=2), encoding="utf-8")
    return path


def load_run(path: str | Path) -> EvalRun:
    return EvalRun.model_validate_json(Path(path).read_text(encoding="utf-8"))

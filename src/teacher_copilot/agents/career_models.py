"""Domain models for the career-guidance agent.

Grounded, honest guidance — not motivational fluff and not invented job titles or
salaries. ``grounding`` mirrors the lesson planner: guidance is ``grounded`` only when
the curated dataset actually matched; otherwise it's clearly labelled ``general``.
``honest_caveats`` is always populated, so guidance never reads as a guarantee.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CareerGrounding = Literal["grounded", "general"]


class MatchedPath(BaseModel):
    """One suggested direction, grounded in a dataset career path when possible."""

    title: str = Field(description="Career path title.")
    why_it_fits: str = Field(description="Why this fits the teacher's situation.")
    skills_to_build: list[str] = Field(default_factory=list)
    first_steps: list[str] = Field(default_factory=list)
    source: str | None = Field(
        default=None, description="Dataset path title this is grounded in (None if general)."
    )


class CareerGuidance(BaseModel):
    """Structured, grounded career guidance."""

    matched_paths: list[MatchedPath] = Field(default_factory=list)
    honest_caveats: list[str] = Field(
        default_factory=list, description="Real tradeoffs — always present."
    )
    grounding: CareerGrounding = "general"
    disclaimer: str | None = Field(
        default=None, description="Set when guidance is general (not dataset-grounded)."
    )

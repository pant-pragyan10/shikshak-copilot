"""Domain models for the lesson-planning agent.

``grounding`` is the trust signal that mirrors the grading agent's "never fabricate"
philosophy: a plan is only ``curriculum_grounded`` when retrieval actually found
relevant curriculum to base it on. ``citations`` are built from real retrieved
chunks, never invented by the model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Grounding = Literal["curriculum_grounded", "partial", "general_knowledge"]


class LessonPlanRequest(BaseModel):
    """A request to plan one lesson."""

    topic: str = Field(description="What the lesson should cover.")
    subject: str | None = Field(default=None)
    grade: str | None = Field(default=None)
    board: str | None = Field(default=None)
    duration_minutes: int = Field(default=40, gt=0, description="Total lesson length.")
    notes: str | None = Field(default=None, description="Extra constraints/preferences.")


class LessonSegment(BaseModel):
    """One timed segment of the lesson."""

    title: str = Field(description="Segment name, e.g. 'Introduction'.")
    minutes: int = Field(ge=0, description="Minutes allotted.")
    activities: list[str] = Field(default_factory=list, description="What happens in this segment.")
    teacher_notes: str = Field(default="", description="Guidance for the teacher.")


class Citation(BaseModel):
    """A provenance pointer into the curriculum corpus."""

    source: str = Field(description="Source filename of the cited chunk.")
    snippet: str = Field(description="Short excerpt of the actual retrieved text.")


class LessonPlan(BaseModel):
    """A structured, optionally curriculum-grounded lesson plan."""

    topic: str
    subject: str | None = None
    grade: str | None = None
    board: str | None = None
    duration_minutes: int = Field(gt=0)

    objectives: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    timeline: list[LessonSegment] = Field(default_factory=list)
    assessment_ideas: list[str] = Field(default_factory=list)
    homework: list[str] = Field(default_factory=list)
    differentiation: list[str] = Field(
        default_factory=list,
        description="Support for mixed-ability classes — a real Indian-classroom need.",
    )

    citations: list[Citation] = Field(default_factory=list)
    grounding: Grounding = Field(
        default="general_knowledge",
        description="How well the plan is backed by retrieved curriculum.",
    )
    disclaimer: str | None = Field(
        default=None, description="Set when the plan is not curriculum-grounded."
    )

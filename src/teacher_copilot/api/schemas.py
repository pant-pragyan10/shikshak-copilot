"""API wire schemas — the contract the frontend mirrors in TypeScript.

Domain models (GradedResult, LessonPlan, CareerGuidance, TeacherProfile, …) are
reused directly where the wire shape is identical to the internal shape. Where they
differ (e.g. we don't want raw image bytes in a JSON body), a dedicated request model
lives here and is converted to the domain model in the route.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from teacher_copilot.agents.grading_models import GradedResult, GradingError, Rubric
from teacher_copilot.memory.profile import Board, WorkloadEntry
from teacher_copilot.orchestrator.state import Intent


# --- errors ---------------------------------------------------------------------
class ErrorBody(BaseModel):
    """The inner error object — a stable, machine-readable shape."""

    type: str = Field(description="Error category, e.g. 'provider_exhausted'.")
    message: str = Field(description="Human-friendly message (never leaks internals).")


class ErrorResponse(BaseModel):
    """Consistent error envelope for every failing endpoint: ``{error: {...}}``."""

    error: ErrorBody


# --- chat -----------------------------------------------------------------------
class ChatRequest(BaseModel):
    teacher_id: str = Field(description="Which teacher is talking (loads their profile).")
    message: str = Field(description="The teacher's message.")
    session_id: str | None = Field(
        default=None, description="Conversation id; omit to start a new session."
    )


class ChatResponse(BaseModel):
    session_id: str
    intent: Intent
    active_agent: str | None
    message: str = Field(description="The assistant's text reply.")
    agent_output: dict[str, Any] | None = Field(
        default=None, description="Structured agent payload for rich rendering, if any."
    )


# --- grading --------------------------------------------------------------------
class GradeRequest(BaseModel):
    """Text-answer grading over JSON (image grading uses the multipart endpoint)."""

    question: str
    answer_text: str = Field(description="The student's typed answer.")
    rubric: Rubric | None = Field(
        default=None, description="Teacher rubric; auto-generated if None."
    )
    student_identifier: str | None = None
    teacher_id: str | None = Field(default=None, description="Optional, for subject/grade context.")


class BatchGradeRequest(BaseModel):
    items: list[GradeRequest] = Field(min_length=1)
    teacher_id: str | None = None
    max_concurrency: int = Field(default=3, ge=1, le=10)


class BatchGradeResponse(BaseModel):
    results: list[GradedResult | GradingError]


# --- profile --------------------------------------------------------------------
class ProfileUpsert(BaseModel):
    """A profile PUT body — ``teacher_id`` comes from the path, not the body."""

    name: str
    subjects: list[str] = Field(default_factory=list)
    grades_taught: list[str] = Field(default_factory=list)
    board: Board = Board.CBSE
    years_experience: int = Field(default=0, ge=0)
    workload_log: list[WorkloadEntry] = Field(default_factory=list)


# --- career ---------------------------------------------------------------------
class CareerRequest(BaseModel):
    interest: str = Field(description="The teacher's career interest / situation.")
    teacher_id: str | None = Field(default=None, description="Optional, for subjects/experience.")

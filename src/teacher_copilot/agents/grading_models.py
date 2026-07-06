"""Domain models for the grading agent.

These are the stable contract for grading — used by the conversational graph node,
the direct/batch API, and the eval harness. Kept in their own module because they
are shared and will outlive any single prompt.

``GradedResult`` carries the rubric the grade was based on (and whether it was the
teacher's or auto-generated) so a teacher can always see *why* a mark was given.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RubricCriterion(BaseModel):
    """One line of a marking rubric."""

    name: str = Field(description="Short criterion name, e.g. 'Conceptual accuracy'.")
    description: str = Field(description="What earns the marks for this criterion.")
    max_marks: int = Field(gt=0, description="Maximum marks for this criterion (> 0).")


class Rubric(BaseModel):
    """A marking rubric: a non-empty list of criteria plus optional context."""

    criteria: list[RubricCriterion] = Field(min_length=1, description="At least one criterion.")
    subject: str | None = Field(default=None, description="Subject, e.g. 'Science'.")
    grade_level: str | None = Field(default=None, description="Class/grade, e.g. '9'.")
    question: str | None = Field(default=None, description="The question this rubric grades.")

    @property
    def total_marks(self) -> int:
        """Sum of the criteria's maximum marks."""
        return sum(c.max_marks for c in self.criteria)


class GradingRequest(BaseModel):
    """A single answer to grade. Exactly one of text/image must be supplied."""

    question: str = Field(description="The question the student was answering.")
    answer_text: str | None = Field(default=None, description="Typed answer, if text.")
    answer_image: bytes | None = Field(default=None, description="Scanned answer image bytes.")
    mime_type: str = Field(default="image/png", description="MIME type of answer_image.")
    rubric: Rubric | None = Field(
        default=None, description="Teacher rubric; auto-generated if None."
    )
    student_identifier: str | None = Field(default=None, description="Optional student label.")

    @model_validator(mode="after")
    def _exactly_one_answer(self) -> GradingRequest:
        has_text = bool(self.answer_text and self.answer_text.strip())
        has_image = self.answer_image is not None
        if has_text == has_image:
            raise ValueError("provide exactly one of answer_text or answer_image")
        return self

    @property
    def is_image(self) -> bool:
        """True if this is an image (scanned) answer."""
        return self.answer_image is not None


class CriterionScore(BaseModel):
    """Marks awarded for one rubric criterion, with a justification."""

    criterion_name: str = Field(description="Name of the rubric criterion.")
    awarded_marks: int = Field(ge=0, description="Marks awarded (0..max_marks).")
    max_marks: int = Field(gt=0, description="Maximum marks for this criterion.")
    justification: str = Field(description="1-2 sentences citing the student's answer.")


class GradedResult(BaseModel):
    """The full result of grading one answer."""

    scores: list[CriterionScore] = Field(description="Per-criterion scores.")
    total_awarded: int = Field(ge=0, description="Sum of awarded marks (computed).")
    total_max: int = Field(ge=0, description="Sum of max marks (computed).")
    percentage: float = Field(ge=0.0, le=100.0, description="total_awarded/total_max (computed).")
    strengths: list[str] = Field(default_factory=list, description="2-3 things done well.")
    improvements: list[str] = Field(
        default_factory=list, description="2-3 actionable, kind next steps."
    )
    overall_comment: str = Field(default="", description="Warm, honest summary comment.")
    status: Literal["graded", "needs_review"] = Field(
        default="graded", description="'needs_review' when a grade must not be trusted/fabricated."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Model's confidence in this grade.")

    # Provenance / bookkeeping (added by the agent, not the model).
    rubric: Rubric | None = Field(default=None, description="Rubric the grade was based on.")
    rubric_source: Literal["teacher", "auto"] = Field(
        default="teacher", description="Whether the rubric was teacher-supplied or auto-generated."
    )
    adjustments: list[str] = Field(
        default_factory=list, description="Consistency-guard notes, e.g. clamped over-max marks."
    )
    raw_output: str | None = Field(
        default=None, description="Raw model text, preserved when parsing failed (needs_review)."
    )


class GradingError(BaseModel):
    """A per-item failure in a batch — so one bad item never sinks the whole batch."""

    message: str = Field(description="Human-readable error description.")
    error_type: str = Field(default="grading_error", description="Exception/type name.")
    student_identifier: str | None = Field(default=None, description="Which item failed, if known.")

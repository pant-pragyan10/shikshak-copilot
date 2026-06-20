"""Teacher profile and workload models.

The :class:`TeacherProfile` is the durable identity/memory record for a teacher.
It is loaded into :class:`~teacher_copilot.orchestrator.state.CopilotState` at the
start of a turn and persisted back by the memory layer (Phase 2). The
:class:`WorkloadEntry` log is the signal source the WellbeingAgent reads (Phase 5).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class Board(StrEnum):
    """The school board a teacher's curriculum aligns to."""

    CBSE = "CBSE"
    ICSE = "ICSE"
    STATE = "STATE"


class WorkloadEntry(BaseModel):
    """A single day's workload signal, appended by the WellbeingAgent (Phase 5).

    Deliberately non-clinical: ``self_reported_energy`` is a simple 1–5 scale, not
    a mood/mental-health measure.
    """

    entry_date: date = Field(description="The day this entry describes.")
    papers_graded: int = Field(default=0, ge=0, description="Papers graded that day.")
    classes_taken: int = Field(default=0, ge=0, description="Classes taught that day.")
    self_reported_energy: int = Field(
        ge=1, le=5, description="Teacher-reported energy for the day (1=low, 5=high)."
    )


class TeacherProfile(BaseModel):
    """Durable profile for a single teacher; the memory layer's core record."""

    name: str = Field(description="Teacher's display name.")
    subjects: list[str] = Field(default_factory=list, description="Subjects taught.")
    grades_taught: list[str] = Field(
        default_factory=list, description="Grade levels taught, e.g. ['6', '7', '10']."
    )
    board: Board = Field(default=Board.CBSE, description="Curriculum board.")
    years_experience: int = Field(default=0, ge=0, description="Years of teaching experience.")
    workload_log: list[WorkloadEntry] = Field(
        default_factory=list, description="Chronological workload signals (WellbeingAgent)."
    )

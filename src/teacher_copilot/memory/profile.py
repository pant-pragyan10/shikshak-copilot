"""Teacher profile and workload models.

The :class:`TeacherProfile` is the durable identity/memory record for a teacher.
It is loaded into :class:`~teacher_copilot.orchestrator.state.CopilotState` at the
start of a turn and persisted back by the memory layer (Phase 2). The
:class:`WorkloadEntry` log is the signal source the WellbeingAgent reads (Phase 5).
"""

from __future__ import annotations

import asyncio
import os
from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from teacher_copilot.config import Settings, get_settings


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

    teacher_id: str = Field(description="Stable unique id; also the profile's filename stem.")
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


class ProfileStore:
    """Persists :class:`TeacherProfile` as one JSON file per teacher.

    Deliberately the simplest thing that works: a directory of JSON files, written
    atomically (temp file + rename). The *interface* is the contract — ``load`` /
    ``save`` / ``append_workload`` — so the backing store can be swapped for SQLite,
    Postgres, or a managed KV in deployment without touching callers. Blocking file
    IO is pushed onto a thread to keep the interface async.
    """

    def __init__(self, settings: Settings | None = None, *, base_path: str | None = None) -> None:
        self._base = Path(base_path or (settings or get_settings()).profile_store_path)

    def _path_for(self, teacher_id: str) -> Path:
        # Guard against path traversal — teacher_id is a filename stem, nothing more.
        if not teacher_id or "/" in teacher_id or "\\" in teacher_id or ".." in teacher_id:
            raise ValueError(f"invalid teacher_id: {teacher_id!r}")
        return self._base / f"{teacher_id}.json"

    async def load(self, teacher_id: str) -> TeacherProfile | None:
        """Return the stored profile for ``teacher_id``, or None if absent."""
        path = self._path_for(teacher_id)

        def _read() -> TeacherProfile | None:
            if not path.exists():
                return None
            return TeacherProfile.model_validate_json(path.read_text(encoding="utf-8"))

        return await asyncio.to_thread(_read)

    async def save(self, profile: TeacherProfile) -> None:
        """Persist ``profile`` atomically (temp file + rename)."""
        path = self._path_for(profile.teacher_id)

        def _write() -> None:
            self._base.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
            os.replace(tmp, path)  # atomic on POSIX & Windows

        await asyncio.to_thread(_write)

    async def append_workload(self, teacher_id: str, entry: WorkloadEntry) -> TeacherProfile:
        """Append a workload entry to ``teacher_id``'s log and persist. Returns the profile."""
        profile = await self.load(teacher_id)
        if profile is None:
            raise ValueError(f"no profile for teacher_id={teacher_id!r}")
        profile.workload_log.append(entry)
        await self.save(profile)
        return profile


@lru_cache(maxsize=1)
def get_profile_store() -> ProfileStore:
    """Return the process-wide :class:`ProfileStore`."""
    return ProfileStore(get_settings())

"""Teacher profile endpoints: load, upsert, and append workload (feeds wellbeing)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from teacher_copilot.api.context import AppContext, get_context
from teacher_copilot.api.schemas import ProfileUpsert
from teacher_copilot.memory.profile import TeacherProfile, WorkloadEntry

router = APIRouter(tags=["profile"], prefix="/profile")


@router.get("/{teacher_id}", response_model=TeacherProfile)
async def get_profile(teacher_id: str, ctx: AppContext = Depends(get_context)) -> TeacherProfile:
    profile = await ctx.profile_store.load(teacher_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return profile


@router.put("/{teacher_id}", response_model=TeacherProfile)
async def put_profile(
    teacher_id: str, body: ProfileUpsert, ctx: AppContext = Depends(get_context)
) -> TeacherProfile:
    """Create or replace a teacher's profile. The path's ``teacher_id`` is authoritative."""
    profile = TeacherProfile(teacher_id=teacher_id, **body.model_dump())
    await ctx.profile_store.save(profile)
    return profile


@router.post("/{teacher_id}/workload", response_model=TeacherProfile)
async def add_workload(
    teacher_id: str, entry: WorkloadEntry, ctx: AppContext = Depends(get_context)
) -> TeacherProfile:
    """Append a day's workload entry (papers, classes, energy) to the teacher's log."""
    try:
        return await ctx.profile_store.append_workload(teacher_id, entry)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Profile not found; create it first."
        ) from exc

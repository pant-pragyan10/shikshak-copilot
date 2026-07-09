"""Direct tool endpoints for the frontend's dedicated pages (structured in/out).

These reuse the exact same agent objects the graph uses — no duplicated logic. They
exist so the frontend's Lesson Plan / Career pages can send a structured request and
get a structured response without going through intent classification.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from teacher_copilot.agents.career_models import CareerGuidance
from teacher_copilot.agents.lesson_plan_models import LessonPlan, LessonPlanRequest
from teacher_copilot.api.context import AppContext, get_context
from teacher_copilot.api.schemas import CareerRequest

router = APIRouter(tags=["tools"])


@router.post("/lesson-plan", response_model=LessonPlan)
async def lesson_plan(
    req: LessonPlanRequest, ctx: AppContext = Depends(get_context)
) -> LessonPlan:
    """Generate a curriculum-grounded lesson plan (structured request → structured plan)."""
    return await ctx.lesson_agent.generate_plan(req)


@router.post("/career", response_model=CareerGuidance)
async def career(req: CareerRequest, ctx: AppContext = Depends(get_context)) -> CareerGuidance:
    """Generate grounded career guidance for a teacher's stated interest."""
    profile = await ctx.profile_store.load(req.teacher_id) if req.teacher_id else None
    return await ctx.career_agent.generate_guidance(req.interest, profile)

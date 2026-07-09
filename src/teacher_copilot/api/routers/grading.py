"""Grading endpoints: text, batch, and the multipart image ('scan an answer sheet')."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from teacher_copilot.agents.grading_models import (
    GradedResult,
    GradingRequest,
    Rubric,
)
from teacher_copilot.api.context import AppContext, get_context
from teacher_copilot.api.schemas import BatchGradeRequest, BatchGradeResponse, GradeRequest
from teacher_copilot.memory.profile import TeacherProfile

router = APIRouter(tags=["grading"])

_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # ~10 MB


async def _load_profile(ctx: AppContext, teacher_id: str | None) -> TeacherProfile | None:
    return await ctx.profile_store.load(teacher_id) if teacher_id else None


@router.post("/grade", response_model=GradedResult)
async def grade(req: GradeRequest, ctx: AppContext = Depends(get_context)) -> GradedResult:
    """Grade a single typed answer against a rubric (auto-generated if none supplied)."""
    grading_request = GradingRequest(
        question=req.question,
        answer_text=req.answer_text,
        rubric=req.rubric,
        student_identifier=req.student_identifier,
    )
    profile = await _load_profile(ctx, req.teacher_id)
    return await ctx.grading_agent.grade_one(grading_request, profile)


@router.post("/grade/batch", response_model=BatchGradeResponse)
async def grade_batch(
    body: BatchGradeRequest, ctx: AppContext = Depends(get_context)
) -> BatchGradeResponse:
    """Grade many typed answers with bounded concurrency; one failure never sinks the batch."""
    requests = [
        GradingRequest(
            question=item.question,
            answer_text=item.answer_text,
            rubric=item.rubric,
            student_identifier=item.student_identifier,
        )
        for item in body.items
    ]
    profile = await _load_profile(ctx, body.teacher_id)
    results = await ctx.grading_agent.grade_batch(
        requests, profile, max_concurrency=body.max_concurrency
    )
    return BatchGradeResponse(results=results)


@router.post("/grade/image", response_model=GradedResult)
async def grade_image(
    ctx: AppContext = Depends(get_context),
    file: UploadFile = File(..., description="Image of the handwritten/scanned answer."),
    question: str = Form(...),
    rubric_json: str | None = Form(default=None, description="Optional Rubric as a JSON string."),
    teacher_id: str | None = Form(default=None),
) -> GradedResult:
    """Grade a scanned/photographed answer via the multimodal (Gemini vision) path."""
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected an image upload, got '{content_type or 'unknown'}'.",
        )
    if file.size is not None and file.size > _MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="Image exceeds 10 MB.")

    data = await file.read()
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="Image exceeds 10 MB.")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty image upload.")

    rubric = Rubric.model_validate_json(rubric_json) if rubric_json else None
    grading_request = GradingRequest(
        question=question, answer_image=data, mime_type=content_type, rubric=rubric
    )
    profile = await _load_profile(ctx, teacher_id)
    return await ctx.grading_agent.grade_one(grading_request, profile)

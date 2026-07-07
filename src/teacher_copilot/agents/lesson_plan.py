"""Lesson planning agent (Phase 4).

Generates CBSE/ICSE-aligned lesson plans **grounded in retrieved curriculum** and
cited to their sources. The trust rule (same spirit as grading's "never fabricate"):
a plan only claims to be curriculum-grounded when retrieval actually found relevant
content. When it finds nothing relevant, the agent says so and returns a clearly
labelled ``general_knowledge`` plan with a disclaimer and no citations — it never
pretends general knowledge is syllabus-aligned.

Lesson plans are ``bulk`` task_type (Gemini bulk tier first — biggest free daily
budget) and cacheable: identical (topic, subject, grade, board, duration) requests
produce an identical prompt over a fixed corpus, so the Phase 1 response cache turns
a repeat request into a free cache hit.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field, ValidationError

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.agents.lesson_plan_models import (
    Citation,
    Grounding,
    LessonPlan,
    LessonPlanRequest,
    LessonSegment,
)
from teacher_copilot.memory.retrieval import RetrievedChunk, Retriever, get_retriever
from teacher_copilot.orchestrator.state import CopilotState, Message
from teacher_copilot.providers.errors import ProviderError
from teacher_copilot.providers.json_utils import JSONExtractionError, extract_json
from teacher_copilot.providers.router import ChatMessage, ProviderRouter, get_router

logger = logging.getLogger("teacher_copilot.agents.lesson_plan")

# A chunk is "relevant" when its raw cosine similarity clears this bar. Using the raw
# dense score (not the pool-normalised final score) is deliberate: normalisation makes
# the best-of-pool ~1.0 even when nothing is truly relevant, so it can't answer "did we
# actually find curriculum?". Two-plus strong chunks => grounded; one => partial.
_DENSE_RELEVANCE = 0.45
_MIN_STRONG_FOR_GROUNDED = 2
_MAX_CITATIONS = 4
_EXCERPT_CHARS = 1200
_PLAN_TEMPERATURE = 0.3

_SCHEMA = (
    '{"objectives": ["..."], "materials": ["..."], '
    '"timeline": [{"title": "...", "minutes": <int>, "activities": ["..."], '
    '"teacher_notes": "..."}], "assessment_ideas": ["..."], "homework": ["..."], '
    '"differentiation": ["support for slower and faster learners"]}'
)

_GROUNDED_SYSTEM = (
    "You are an experienced CBSE/ICSE teacher in India writing a practical lesson "
    "plan. Base the plan ONLY on the curriculum excerpts provided — do not introduce "
    "syllabus topics the excerpts do not support. Ground objectives and activities in "
    "those excerpts. Plan for a real, mixed-ability Indian classroom (include "
    "differentiation for slower and faster learners) and keep the timeline within the "
    "requested duration.\n\nOutput ONLY this JSON, no prose:\n" + _SCHEMA
)

_GENERAL_SYSTEM = (
    "You are an experienced teacher in India writing a practical lesson plan. No "
    "curriculum excerpts were found for this topic, so plan from general knowledge. Do "
    "NOT claim alignment to any specific board's syllabus. Plan for a real, "
    "mixed-ability Indian classroom (include differentiation) within the requested "
    "duration.\n\nOutput ONLY this JSON, no prose:\n" + _SCHEMA
)

_GENERAL_DISCLAIMER = (
    "No matching curriculum was found in the corpus for this topic, so this plan is "
    "based on general knowledge and is NOT verified against a specific board syllabus. "
    "Please cross-check it against your prescribed textbook."
)

_DURATION_RE = re.compile(r"(\d{2,3})\s*(?:min|minute|minutes|mins)\b", re.IGNORECASE)


class _LLMSegment(BaseModel):
    title: str = ""
    minutes: int = 0
    activities: list[str] = Field(default_factory=list)
    teacher_notes: str = ""


class _LLMLessonPlan(BaseModel):
    """Lenient shape of the planning model's JSON (citations/grounding added by us)."""

    objectives: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    timeline: list[_LLMSegment] = Field(default_factory=list)
    assessment_ideas: list[str] = Field(default_factory=list)
    homework: list[str] = Field(default_factory=list)
    differentiation: list[str] = Field(default_factory=list)


class LessonPlanAgent(BaseAgent):
    """Curriculum-grounded lesson plan generator."""

    name = "lesson_plan"
    description = "Generates CBSE/ICSE-aligned, citation-grounded lesson plans via RAG."

    def __init__(
        self, *, router: ProviderRouter | None = None, retriever: Retriever | None = None
    ) -> None:
        self._router = router
        self._retriever = retriever

    @property
    def router(self) -> ProviderRouter:
        return self._router if self._router is not None else get_router()

    @property
    def retriever(self) -> Retriever:
        return self._retriever if self._retriever is not None else get_retriever()

    async def run(self, state: CopilotState) -> CopilotState:
        """Generate a lesson plan for the latest turn and write it into ``state``."""
        request = self._request_from_state(state)
        state.active_agent = self.name
        try:
            plan = await self.generate_plan(request)
        except Exception as exc:  # final safety net — the graph must never crash
            logger.exception("lesson planning failed unexpectedly")
            plan = _degraded_plan(request, "general_knowledge", f"Planning failed: {exc}")

        state.agent_output = {"type": "lesson_plan", **plan.model_dump()}
        state.metadata["lesson_grounding"] = plan.grounding
        state.messages.append(Message(role="assistant", content=_format_summary(plan)))
        return state

    async def generate_plan(self, request: LessonPlanRequest) -> LessonPlan:
        """Retrieve curriculum, ground the plan on it, and return a cited LessonPlan."""
        chunks = await self._retrieve(request)
        strong = [c for c in chunks if c.dense_score >= _DENSE_RELEVANCE]

        if not strong:
            grounding: Grounding = "general_knowledge"
            context_chunks: list[RetrievedChunk] = []
        elif len(strong) >= _MIN_STRONG_FOR_GROUNDED:
            grounding, context_chunks = "curriculum_grounded", strong
        else:
            grounding, context_chunks = "partial", strong

        messages = _build_messages(request, context_chunks, grounded=bool(context_chunks))
        parsed = await self._call_model(messages)
        if parsed is None:
            return _degraded_plan(
                request, grounding, "The lesson plan could not be generated reliably."
            )

        return _assemble_plan(request, parsed, grounding, context_chunks)

    async def _retrieve(self, request: LessonPlanRequest) -> list[RetrievedChunk]:
        query = f"{request.topic} {request.subject or ''}".strip()
        try:
            return await self.retriever.retrieve(
                query,
                subject=request.subject,
                grade=request.grade,
                board=request.board,
                limit=6,
            )
        except Exception as exc:  # embedder/store trouble must degrade, not crash
            logger.warning("curriculum retrieval failed, planning from general knowledge: %s", exc)
            return []

    async def _call_model(self, messages: list[ChatMessage]) -> _LLMLessonPlan | None:
        """Call the bulk tier with one corrective retry; None if unparseable."""
        for attempt in range(2):
            try:
                completion = await self.router.complete(
                    messages,
                    task_type="bulk",
                    json_mode=True,
                    cacheable=True,
                    temperature=_PLAN_TEMPERATURE,
                    max_tokens=2048,
                )
            except ProviderError as exc:
                logger.warning("lesson plan provider call failed: %s", exc)
                return None
            parsed = _parse_plan(completion.text)
            if parsed is not None:
                return parsed
            if attempt == 0:
                messages = [
                    *messages,
                    ChatMessage(role="assistant", content=completion.text),
                    ChatMessage(
                        role="user",
                        content="That was not valid JSON in the required schema. "
                        "Reply with ONLY the JSON object.",
                    ),
                ]
        return None

    def _request_from_state(self, state: CopilotState) -> LessonPlanRequest:
        text = _last_user_text(state) or ""
        profile = state.teacher_profile
        duration = 40
        match = _DURATION_RE.search(text)
        if match:
            duration = int(match.group(1))
        return LessonPlanRequest(
            topic=text or "(unspecified topic)",
            subject=_first(profile.subjects) if profile else None,
            grade=_first(profile.grades_taught) if profile else None,
            board=str(profile.board) if profile else None,
            duration_minutes=duration,
        )


# --- module-level helpers -------------------------------------------------------


def _first(items: list[str]) -> str | None:
    return items[0] if items else None


def _last_user_text(state: CopilotState) -> str | None:
    for message in reversed(state.messages):
        if message.role == "user":
            return message.content if isinstance(message.content, str) else None
    return None


def _parse_plan(text: str) -> _LLMLessonPlan | None:
    try:
        data = extract_json(text)
    except JSONExtractionError:
        return None
    try:
        return _LLMLessonPlan.model_validate(data)
    except ValidationError:
        return None


def _build_messages(
    request: LessonPlanRequest, chunks: list[RetrievedChunk], *, grounded: bool
) -> list[ChatMessage]:
    header_lines = [
        f"Topic: {request.topic}",
        f"Subject: {request.subject or 'unspecified'}",
        f"Class/Grade: {request.grade or 'unspecified'}",
        f"Board: {request.board or 'unspecified'}",
        f"Duration: {request.duration_minutes} minutes",
    ]
    if request.notes:
        header_lines.append(f"Notes: {request.notes}")
    header = "\n".join(header_lines)

    if grounded:
        excerpts = "\n\n".join(
            f"[{i + 1}] (source: {c.source})\n{c.text[:_EXCERPT_CHARS]}"
            for i, c in enumerate(chunks)
        )
        user = f"{header}\n\nCurriculum excerpts to base the plan on:\n{excerpts}"
        system = _GROUNDED_SYSTEM
    else:
        user = header
        system = _GENERAL_SYSTEM
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def _citations_from(chunks: list[RetrievedChunk]) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.source in seen:
            continue
        seen.add(chunk.source)
        snippet = " ".join(chunk.text.split())[:200]
        citations.append(Citation(source=chunk.source, snippet=snippet))
        if len(citations) >= _MAX_CITATIONS:
            break
    return citations


def _assemble_plan(
    request: LessonPlanRequest,
    parsed: _LLMLessonPlan,
    grounding: Grounding,
    chunks: list[RetrievedChunk],
) -> LessonPlan:
    timeline = [
        LessonSegment(
            title=seg.title,
            minutes=max(0, seg.minutes),
            activities=seg.activities,
            teacher_notes=seg.teacher_notes,
        )
        for seg in parsed.timeline
    ]
    return LessonPlan(
        topic=request.topic,
        subject=request.subject,
        grade=request.grade,
        board=request.board,
        duration_minutes=request.duration_minutes,
        objectives=parsed.objectives,
        materials=parsed.materials,
        timeline=timeline,
        assessment_ideas=parsed.assessment_ideas,
        homework=parsed.homework,
        differentiation=parsed.differentiation,
        citations=_citations_from(chunks) if grounding != "general_knowledge" else [],
        grounding=grounding,
        disclaimer=_GENERAL_DISCLAIMER if grounding == "general_knowledge" else None,
    )


def _degraded_plan(request: LessonPlanRequest, grounding: Grounding, reason: str) -> LessonPlan:
    return LessonPlan(
        topic=request.topic,
        subject=request.subject,
        grade=request.grade,
        board=request.board,
        duration_minutes=request.duration_minutes,
        objectives=["A teacher should draft this lesson manually — automated planning failed."],
        grounding=grounding,
        disclaimer=reason,
    )


def _format_summary(plan: LessonPlan) -> str:
    badge = {
        "curriculum_grounded": "✅ Curriculum-grounded",
        "partial": "◐ Partially grounded",
        "general_knowledge": "⚠️ General knowledge (not syllabus-verified)",
    }[plan.grounding]
    lines = [f"**Lesson plan: {plan.topic}** — {badge}"]
    if plan.disclaimer:
        lines.append(f"_{plan.disclaimer}_")
    if plan.objectives:
        lines.append("\n**Objectives:** " + "; ".join(plan.objectives))
    for seg in plan.timeline:
        activities = "; ".join(seg.activities)
        lines.append(f"- **{seg.title}** ({seg.minutes} min): {activities}")
    if plan.differentiation:
        lines.append("\n**Differentiation:** " + "; ".join(plan.differentiation))
    if plan.citations:
        sources = ", ".join(sorted({c.source for c in plan.citations}))
        lines.append(f"\n_Sources: {sources}_")
    return "\n".join(lines)

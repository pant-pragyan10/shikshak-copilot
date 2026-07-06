"""Grading agent (Phase 3) — the flagship feature.

Grades typed or scanned student answers against a rubric and returns structured,
teacher-style feedback. Design principles:

- **Never fabricate a grade.** If an answer can't be read, looks like it answers a
  different question, or the model is unsure, we return ``status="needs_review"``
  rather than invent marks.
- **Always show the rubric.** If the teacher didn't supply one, we generate it and
  return it in the result so the grade is explainable.
- **Grade only against the rubric**, cite the student's own words, and keep the tone
  kind but honest — this should read like a good teacher's margin notes.
- **Bounded batch concurrency.** Free-tier RPM limits make unbounded fan-out
  self-defeating, so batch grading runs through an ``asyncio.Semaphore``.

Text answers use the ``smart`` tier; scanned images use the ``multimodal`` tier
(Gemini vision) via :class:`~teacher_copilot.providers.types.ImagePart`.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.agents.grading_models import (
    CriterionScore,
    GradedResult,
    GradingError,
    GradingRequest,
    Rubric,
    RubricCriterion,
)
from teacher_copilot.memory.profile import TeacherProfile
from teacher_copilot.orchestrator.state import CopilotState, Message
from teacher_copilot.providers.errors import ProviderError
from teacher_copilot.providers.json_utils import JSONExtractionError, extract_json
from teacher_copilot.providers.router import ProviderRouter, get_router
from teacher_copilot.providers.types import ChatMessage, ImagePart, TaskType, TextPart

logger = logging.getLogger("teacher_copilot.agents.grading")

_GRADE_TEMPERATURE = 0.2

_RUBRIC_SYSTEM_PROMPT = """\
You are an experienced CBSE/ICSE teacher in India writing a marking rubric.
Given a question (and any subject/grade context), produce a concise rubric of 2-4
criteria that together total a sensible number of marks for such a question
(usually 3-10). Each criterion needs a short name, a description of what earns the
marks, and a positive integer max_marks.

Output ONLY this JSON, no prose:
{"criteria": [{"name": "...", "description": "...", "max_marks": <int>}]}"""

_GRADE_SYSTEM_PROMPT = """\
You are grading a school student's answer in the Indian context (CBSE/ICSE,
marks-based). Rules:
- Grade ONLY against the provided rubric. Do not invent criteria.
- For each criterion, award whole marks between 0 and its max, and justify by
  quoting or referencing specific parts of the student's answer.
- Be kind but honest, like a good teacher's margin notes — not a cold verdict.
- If the answer is illegible/unreadable, appears to answer a DIFFERENT question, or
  you are not confident, set status to "needs_review" and DO NOT fabricate marks.

Output ONLY this JSON, matching the schema exactly, no prose:
{"scores": [{"criterion_name": "...", "awarded_marks": <int>, "justification": "..."}],
 "strengths": ["...", "..."], "improvements": ["...", "..."],
 "overall_comment": "...", "status": "graded" | "needs_review",
 "confidence": <float 0.0-1.0>}"""


class _LLMScore(BaseModel):
    """Lenient per-criterion score as emitted by the model (clamped later)."""

    criterion_name: str
    awarded_marks: float = 0.0
    justification: str = ""


class _LLMGradeOutput(BaseModel):
    """Lenient shape of the grading model's JSON, pre-validation/clamping."""

    scores: list[_LLMScore] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    overall_comment: str = ""
    status: str = "graded"
    confidence: float = 0.5


class _LLMRubricOutput(BaseModel):
    """Lenient shape of the rubric-generation model's JSON."""

    criteria: list[RubricCriterion] = Field(default_factory=list)


def _split_question_answer(text: str) -> tuple[str | None, str | None]:
    """Best-effort split of a free-form message into (question, answer).

    Recognises an explicit ``answer:`` marker (optionally preceded by ``question:``).
    Returns ``(None, None)`` when no marker is found so the caller can decide.
    """
    lowered = text.lower()
    if "answer:" in lowered:
        idx = lowered.rfind("answer:")
        question = re.sub(
            r"^\s*question\s*:\s*", "", text[:idx].strip(), flags=re.IGNORECASE
        ).strip()
        answer = text[idx + len("answer:") :].strip()
        return (question or None), (answer or None)
    return None, None


class GradingAgent(BaseAgent):
    """Rubric-based grader for typed and scanned student answers."""

    name = "grading"
    description = "Grades typed or scanned student answers against a rubric."

    def __init__(self, *, router: ProviderRouter | None = None) -> None:
        self._router = router

    @property
    def router(self) -> ProviderRouter:
        return self._router if self._router is not None else get_router()

    # --- graph (conversational) entry point ------------------------------------

    async def run(self, state: CopilotState) -> CopilotState:
        """Grade the answer in the latest turn and write feedback into ``state``.

        Never raises: any failure degrades to a ``needs_review`` result so the graph
        keeps running.
        """
        request = self._request_from_state(state)
        state.active_agent = self.name
        if request is None:
            reply = (
                "I couldn't find a student answer to grade. Paste the question and the "
                "student's answer (e.g. 'Question: ... Answer: ...'), or attach the "
                "answer sheet image."
            )
            state.agent_output = {"type": "grading", "status": "needs_input", "message": reply}
            state.messages.append(Message(role="assistant", content=reply))
            return state

        try:
            result = await self.grade_one(request, state.teacher_profile)
        except Exception as exc:  # final safety net — the graph must never crash
            logger.exception("grading failed unexpectedly")
            result = _needs_review_result(
                request.rubric, f"Grading failed unexpectedly: {exc}", raw=None
            )
            if request.rubric is None:
                result.rubric_source = "auto"

        state.agent_output = {"type": "grading", **result.model_dump()}
        if result.raw_output:
            state.metadata["grading_raw"] = result.raw_output
        if result.adjustments:
            state.metadata["grading_adjustments"] = result.adjustments
        state.messages.append(Message(role="assistant", content=_format_summary(result)))
        return state

    # --- direct / batch API ----------------------------------------------------

    async def grade_one(
        self, request: GradingRequest, profile: TeacherProfile | None = None
    ) -> GradedResult:
        """Grade a single request. Generates a rubric first if none was supplied."""
        source: Literal["teacher", "auto"]
        if request.rubric is not None:
            rubric, source = request.rubric, "teacher"
        else:
            rubric, source = await self._generate_rubric(request, profile), "auto"

        result = await self._grade(request, rubric)
        result.rubric = rubric
        result.rubric_source = source
        return result

    async def grade_batch(
        self,
        requests: list[GradingRequest],
        profile: TeacherProfile | None = None,
        *,
        max_concurrency: int = 3,
    ) -> list[GradedResult | GradingError]:
        """Grade many answers with bounded concurrency.

        Concurrency is capped by a semaphore because the free provider tiers have low
        RPM limits — firing all requests at once just trips 429s and is slower overall.
        A single failed item is wrapped as :class:`GradingError`; it never sinks the
        rest of the batch.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _guarded(req: GradingRequest) -> GradedResult:
            async with semaphore:
                return await self.grade_one(req, profile)

        settled = await asyncio.gather(
            *(_guarded(req) for req in requests), return_exceptions=True
        )
        results: list[GradedResult | GradingError] = []
        for req, outcome in zip(requests, settled, strict=True):
            if isinstance(outcome, BaseException):
                results.append(
                    GradingError(
                        message=str(outcome),
                        error_type=type(outcome).__name__,
                        student_identifier=req.student_identifier,
                    )
                )
            else:
                results.append(outcome)
        return results

    # --- internals -------------------------------------------------------------

    async def _generate_rubric(
        self, request: GradingRequest, profile: TeacherProfile | None
    ) -> Rubric:
        """Auto-generate a rubric from the question + profile context.

        Falls back to a sensible default rubric if the model fails — grading should
        still proceed (and the rubric is shown to the teacher regardless).
        """
        subject = profile.subjects[0] if profile and profile.subjects else None
        grade_level = profile.grades_taught[0] if profile and profile.grades_taught else None
        context = _rubric_context(request.question, subject, grade_level)
        messages = [
            ChatMessage(role="system", content=_RUBRIC_SYSTEM_PROMPT),
            ChatMessage(role="user", content=context),
        ]
        try:
            completion = await self.router.complete(
                messages, task_type="smart", json_mode=True, temperature=_GRADE_TEMPERATURE
            )
            parsed = _LLMRubricOutput.model_validate(extract_json(completion.text))
            if parsed.criteria:
                return Rubric(
                    criteria=parsed.criteria,
                    subject=subject,
                    grade_level=grade_level,
                    question=request.question,
                )
        except (ProviderError, JSONExtractionError, ValidationError) as exc:
            logger.warning("rubric auto-generation failed, using default: %s", exc)
        return _default_rubric(request.question, subject, grade_level)

    async def _grade(self, request: GradingRequest, rubric: Rubric) -> GradedResult:
        """Run the grading model with one corrective retry; needs_review on failure."""
        messages = _build_grade_messages(request, rubric)
        task_type: TaskType = "multimodal" if request.is_image else "smart"
        raw: str | None = None

        for attempt in range(2):
            try:
                completion = await self.router.complete(
                    messages, task_type=task_type, json_mode=True, temperature=_GRADE_TEMPERATURE
                )
            except ProviderError as exc:
                logger.warning("grading provider call failed: %s", exc)
                return _needs_review_result(
                    rubric, "The grading service was unavailable — please try again.", raw=None
                )
            raw = completion.text
            parsed = _parse_grade(raw)
            if parsed is not None:
                return _assemble_result(parsed, rubric)
            if attempt == 0:
                messages.append(ChatMessage(role="assistant", content=raw))
                messages.append(
                    ChatMessage(
                        role="user",
                        content="That was not valid JSON in the required schema. "
                        "Reply with ONLY the JSON object, nothing else.",
                    )
                )

        logger.info("grading output unparseable after retry; flagging needs_review")
        return _needs_review_result(
            rubric, "The automated grade could not be parsed reliably; please review.", raw=raw
        )

    def _request_from_state(self, state: CopilotState) -> GradingRequest | None:
        """Build a GradingRequest from the latest user turn + any image in metadata."""
        text = _last_user_text(state)
        image = state.metadata.get("answer_image")
        mime = str(state.metadata.get("answer_image_mime", "image/png"))

        if isinstance(image, bytes) and image:
            question, _ = _split_question_answer(text or "")
            return GradingRequest(
                question=question or "(Question not stated; infer it from the answer image.)",
                answer_image=image,
                mime_type=mime,
            )
        if not text:
            return None
        question, answer = _split_question_answer(text)
        try:
            return GradingRequest(
                question=question or "(The question is not stated; infer it from the answer.)",
                answer_text=answer or text,
            )
        except ValidationError:
            return None


# --- module-level helpers (pure, easy to test) ---------------------------------


def _last_user_text(state: CopilotState) -> str | None:
    for message in reversed(state.messages):
        if message.role == "user":
            return message.content if isinstance(message.content, str) else None
    return None


def _rubric_context(question: str, subject: str | None, grade_level: str | None) -> str:
    lines = [f"Question: {question}"]
    if subject:
        lines.append(f"Subject: {subject}")
    if grade_level:
        lines.append(f"Class/Grade: {grade_level}")
    return "\n".join(lines)


def _default_rubric(question: str, subject: str | None, grade_level: str | None) -> Rubric:
    """A neutral fallback rubric used only when auto-generation fails."""
    return Rubric(
        criteria=[
            RubricCriterion(
                name="Correctness",
                description="Accuracy of the key facts, concepts, or reasoning.",
                max_marks=3,
            ),
            RubricCriterion(
                name="Completeness",
                description="Covers the main points the question asks for.",
                max_marks=2,
            ),
            RubricCriterion(
                name="Clarity",
                description="Clear, well-organised expression.",
                max_marks=1,
            ),
        ],
        subject=subject,
        grade_level=grade_level,
        question=question,
    )


def _build_grade_messages(request: GradingRequest, rubric: Rubric) -> list[ChatMessage]:
    rubric_lines = "\n".join(
        f"- {c.name} (max {c.max_marks}): {c.description}" for c in rubric.criteria
    )
    header = (
        f"Question:\n{request.question}\n\n"
        f"Rubric (total {rubric.total_marks} marks):\n{rubric_lines}\n\n"
    )
    system = ChatMessage(role="system", content=_GRADE_SYSTEM_PROMPT)
    if request.is_image and request.answer_image is not None:
        user = ChatMessage(
            role="user",
            content=[
                TextPart(text=header + "Student answer is in the attached image."),
                ImagePart(data=request.answer_image, mime_type=request.mime_type),
            ],
        )
    else:
        user = ChatMessage(
            role="user",
            content=header + f"Student answer:\n{request.answer_text}",
        )
    return [system, user]


def _parse_grade(text: str) -> _LLMGradeOutput | None:
    try:
        data = extract_json(text)
    except JSONExtractionError:
        return None
    try:
        return _LLMGradeOutput.model_validate(data)
    except ValidationError:
        return None


def _assemble_result(parsed: _LLMGradeOutput, rubric: Rubric) -> GradedResult:
    """Align model scores to the rubric, clamp to bounds, and compute totals."""
    by_name = {s.criterion_name.strip().lower(): s for s in parsed.scores}
    scores: list[CriterionScore] = []
    adjustments: list[str] = []

    for criterion in rubric.criteria:
        llm = by_name.get(criterion.name.strip().lower())
        awarded = int(round(llm.awarded_marks)) if llm else 0
        justification = (
            llm.justification if llm and llm.justification else "Not addressed by the grader."
        )
        if awarded > criterion.max_marks:
            adjustments.append(
                f"Clamped '{criterion.name}' from {awarded} to {criterion.max_marks} (over max)."
            )
            awarded = criterion.max_marks
        elif awarded < 0:
            adjustments.append(f"Clamped '{criterion.name}' from {awarded} to 0.")
            awarded = 0
        scores.append(
            CriterionScore(
                criterion_name=criterion.name,
                awarded_marks=awarded,
                max_marks=criterion.max_marks,
                justification=justification,
            )
        )

    total_awarded = sum(s.awarded_marks for s in scores)
    total_max = rubric.total_marks
    percentage = round(100 * total_awarded / total_max, 1) if total_max else 0.0
    status: Literal["graded", "needs_review"] = (
        "needs_review" if parsed.status == "needs_review" else "graded"
    )
    confidence = max(0.0, min(1.0, parsed.confidence))

    return GradedResult(
        scores=scores,
        total_awarded=total_awarded,
        total_max=total_max,
        percentage=percentage,
        strengths=parsed.strengths[:3],
        improvements=parsed.improvements[:3],
        overall_comment=parsed.overall_comment,
        status=status,
        confidence=confidence,
        adjustments=adjustments,
    )


def _needs_review_result(rubric: Rubric | None, reason: str, *, raw: str | None) -> GradedResult:
    return GradedResult(
        scores=[],
        total_awarded=0,
        total_max=rubric.total_marks if rubric else 0,
        percentage=0.0,
        strengths=[],
        improvements=[],
        overall_comment=reason,
        status="needs_review",
        confidence=0.0,
        rubric=rubric,
        adjustments=[],
        raw_output=raw,
    )


def _format_summary(result: GradedResult) -> str:
    """A human-readable margin-note summary for the conversational reply."""
    if result.status == "needs_review":
        return f"⚠️ Needs review: {result.overall_comment}"
    lines = [f"**Score: {result.total_awarded}/{result.total_max} ({result.percentage}%)**"]
    if result.rubric_source == "auto":
        lines.append("_(graded against an auto-generated rubric, shown below)_")
    for score in result.scores:
        lines.append(
            f"- {score.criterion_name}: {score.awarded_marks}/{score.max_marks} — "
            f"{score.justification}"
        )
    if result.strengths:
        lines.append("\n**Strengths:** " + "; ".join(result.strengths))
    if result.improvements:
        lines.append("**To improve:** " + "; ".join(result.improvements))
    if result.overall_comment:
        lines.append("\n" + result.overall_comment)
    return "\n".join(lines)

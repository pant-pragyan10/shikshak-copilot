"""Grading agent tests — all LLM calls mocked, no network."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from pydantic import ValidationError

from teacher_copilot.agents.grading import GradingAgent
from teacher_copilot.agents.grading_models import (
    GradedResult,
    GradingError,
    GradingRequest,
    Rubric,
    RubricCriterion,
)
from teacher_copilot.orchestrator.state import CopilotState, Message
from teacher_copilot.providers.types import CompletionResult, Provider

# --- fixtures / fakes -----------------------------------------------------------

RUBRIC = Rubric(
    criteria=[
        RubricCriterion(name="Accuracy", description="Correct facts.", max_marks=3),
        RubricCriterion(name="Clarity", description="Clear expression.", max_marks=2),
    ]
)

GRADE_JSON = json.dumps(
    {
        "scores": [
            {"criterion_name": "Accuracy", "awarded_marks": 3, "justification": "All correct."},
            {"criterion_name": "Clarity", "awarded_marks": 1, "justification": "A bit terse."},
        ],
        "strengths": ["Accurate", "Concise"],
        "improvements": ["Add an example"],
        "overall_comment": "Solid answer.",
        "status": "graded",
        "confidence": 0.85,
    }
)

RUBRIC_JSON = json.dumps(
    {
        "criteria": [
            {"name": "Accuracy", "description": "Correct facts.", "max_marks": 4},
            {"name": "Clarity", "description": "Clear.", "max_marks": 2},
        ]
    }
)


class FakeRouter:
    """Router stand-in: ordered responses, call recording, concurrency + failure hooks."""

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        delay: float = 0.0,
        raise_on: str | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.delay = delay
        self.raise_on = raise_on
        self.calls: list[tuple[str, bool, bool]] = []  # (task_type, json_mode, has_images)
        self._i = 0
        self._inflight = 0
        self.max_inflight = 0

    async def complete(
        self,
        messages: list[Any],
        *,
        task_type: str = "fast",
        json_mode: bool = False,
        **kwargs: Any,
    ) -> CompletionResult:
        self._inflight += 1
        self.max_inflight = max(self.max_inflight, self._inflight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            has_images = any(
                (not isinstance(m.content, str)) and m.has_images() for m in messages
            )
            user_text = " ".join(m.as_text() for m in messages if m.role == "user")
            self.calls.append((task_type, json_mode, has_images))
            if self.raise_on and self.raise_on in user_text:
                raise RuntimeError("boom")
            text = self.responses[min(self._i, len(self.responses) - 1)] if self.responses else "{}"
            self._i += 1
            provider = Provider.GEMINI if has_images else Provider.GROQ
            return CompletionResult(text=text, provider=provider, model="m")
        finally:
            self._inflight -= 1


def _text_request(rubric: Rubric | None = RUBRIC) -> GradingRequest:
    return GradingRequest(
        question="What is photosynthesis?",
        answer_text="Plants make food using sunlight.",
        rubric=rubric,
    )


# --- request validation ---------------------------------------------------------


def test_request_rejects_both_text_and_image() -> None:
    with pytest.raises(ValidationError):
        GradingRequest(question="q", answer_text="a", answer_image=b"x")


def test_request_rejects_neither_text_nor_image() -> None:
    with pytest.raises(ValidationError):
        GradingRequest(question="q")


# --- grading paths --------------------------------------------------------------


async def test_text_grading_happy_path() -> None:
    router = FakeRouter([GRADE_JSON])
    result = await GradingAgent(router=router).grade_one(_text_request())

    assert isinstance(result, GradedResult)
    assert result.status == "graded"
    assert result.rubric_source == "teacher"
    assert result.total_awarded == 4  # 3 + 1
    assert result.total_max == 5
    assert result.percentage == 80.0
    assert sum(s.awarded_marks for s in result.scores) == result.total_awarded
    assert router.calls == [("smart", True, False)]  # text -> smart tier


async def test_rubric_auto_generation() -> None:
    router = FakeRouter([RUBRIC_JSON, GRADE_JSON])
    result = await GradingAgent(router=router).grade_one(_text_request(rubric=None))

    assert result.rubric_source == "auto"
    assert result.rubric is not None
    assert [c.name for c in result.rubric.criteria] == ["Accuracy", "Clarity"]
    assert result.status == "graded"
    # first call generates the rubric, second grades
    assert len(router.calls) == 2
    assert router.calls[0][0] == "smart" and router.calls[0][1] is True


async def test_image_request_routes_multimodal() -> None:
    router = FakeRouter([GRADE_JSON])
    request = GradingRequest(
        question="Label the diagram.", answer_image=b"\x89PNG-fake", mime_type="image/png",
        rubric=RUBRIC,
    )
    await GradingAgent(router=router).grade_one(request)

    assert router.calls[-1][0] == "multimodal"
    assert router.calls[-1][2] is True  # message carried an image part


async def test_malformed_json_retries_then_needs_review() -> None:
    router = FakeRouter(["not json", "still not json"])
    result = await GradingAgent(router=router).grade_one(_text_request())

    assert result.status == "needs_review"
    assert result.raw_output == "still not json"  # raw preserved
    assert len(router.calls) == 2  # initial + one corrective retry
    assert result.total_awarded == 0  # never fabricates marks


async def test_marks_exceeding_max_are_clamped_and_flagged() -> None:
    over_max = json.dumps(
        {
            "scores": [
                {"criterion_name": "Accuracy", "awarded_marks": 9, "justification": "x"},
                {"criterion_name": "Clarity", "awarded_marks": 2, "justification": "y"},
            ],
            "strengths": [],
            "improvements": [],
            "overall_comment": "",
            "status": "graded",
            "confidence": 0.7,
        }
    )
    router = FakeRouter([over_max])
    result = await GradingAgent(router=router).grade_one(_text_request())

    accuracy = next(s for s in result.scores if s.criterion_name == "Accuracy")
    assert accuracy.awarded_marks == 3  # clamped to max
    assert result.adjustments  # flagged
    assert result.total_awarded == 5  # 3 + 2, internally consistent


# --- batch ----------------------------------------------------------------------


async def test_batch_bounded_concurrency() -> None:
    router = FakeRouter([GRADE_JSON], delay=0.02)
    requests = [_text_request() for _ in range(6)]
    results = await GradingAgent(router=router).grade_batch(requests, max_concurrency=2)

    assert len(results) == 6
    assert all(isinstance(r, GradedResult) for r in results)
    assert router.max_inflight <= 2  # semaphore held the line


async def test_batch_one_failure_does_not_sink_others() -> None:
    router = FakeRouter([GRADE_JSON], raise_on="EXPLODE")
    requests = [
        _text_request(),
        GradingRequest(
            question="q", answer_text="EXPLODE please", rubric=RUBRIC, student_identifier="bad"
        ),
        _text_request(),
    ]
    results = await GradingAgent(router=router).grade_batch(requests, max_concurrency=3)

    assert len(results) == 3
    errors = [r for r in results if isinstance(r, GradingError)]
    graded = [r for r in results if isinstance(r, GradedResult)]
    assert len(errors) == 1
    assert len(graded) == 2
    assert errors[0].student_identifier == "bad"


# --- conversational graph node --------------------------------------------------


async def test_run_produces_grading_output() -> None:
    router = FakeRouter([GRADE_JSON])
    state = CopilotState(
        messages=[
            Message(
                role="user",
                content="Question: What is photosynthesis? Answer: Plants make food from sunlight.",
            )
        ]
    )
    updated = await GradingAgent(router=router).run(state)

    assert updated.active_agent == "grading"
    assert updated.agent_output is not None
    assert updated.agent_output["type"] == "grading"
    assert updated.agent_output["status"] == "graded"
    assert updated.messages[-1].role == "assistant"


async def test_run_without_answer_asks_for_input() -> None:
    router = FakeRouter([GRADE_JSON])
    state = CopilotState(messages=[Message(role="user", content="")])
    updated = await GradingAgent(router=router).run(state)

    assert updated.agent_output is not None
    assert updated.agent_output["status"] == "needs_input"

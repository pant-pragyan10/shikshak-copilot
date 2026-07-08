"""Orchestrator tests: intent classification and end-to-end graph routing (mocked LLM)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from teacher_copilot.memory.profile import ProfileStore
from teacher_copilot.orchestrator.graph import build_graph, run_turn
from teacher_copilot.orchestrator.intent import classify_intent
from teacher_copilot.orchestrator.state import CopilotState, Intent, Message
from teacher_copilot.providers.types import CompletionResult, Provider


class FakeRouter:
    """Router stand-in. JSON-mode calls (intent) and text calls (general) differ.

    ``json_sequence`` overrides the JSON responses call-by-call for retry testing.
    """

    def __init__(
        self,
        *,
        intent: str = "general",
        confidence: float = 0.95,
        reply: str = "Sure, happy to help!",
        json_sequence: list[str] | None = None,
    ) -> None:
        self.intent = intent
        self.confidence = confidence
        self.reply = reply
        self.json_sequence = json_sequence
        self.json_calls = 0
        self.text_calls = 0

    async def complete(
        self, messages: list[Any], *, json_mode: bool = False, **kwargs: Any
    ) -> CompletionResult:
        if json_mode:
            if self.json_sequence is not None:
                idx = min(self.json_calls, len(self.json_sequence) - 1)
                text = self.json_sequence[idx]
            else:
                text = json.dumps({"intent": self.intent, "confidence": self.confidence})
            self.json_calls += 1
            return CompletionResult(text=text, provider=Provider.GROQ, model="m")
        self.text_calls += 1
        return CompletionResult(text=self.reply, provider=Provider.GROQ, model="m")


def _state(text: str) -> CopilotState:
    return CopilotState(messages=[Message(role="user", content=text)])


# --- intent classification ------------------------------------------------------


async def test_intent_json_happy_path() -> None:
    router = FakeRouter(intent="lesson_plan", confidence=0.9)
    result = await classify_intent(_state("plan chapter 4 of class 8 maths"), router=router)
    assert result.intent is Intent.LESSON_PLAN
    assert result.metadata["intent_source"] == "llm"
    assert result.metadata["intent_confidence"] == 0.9


async def test_malformed_json_retries_then_heuristic() -> None:
    router = FakeRouter(json_sequence=["not json at all", "still {broken"])
    result = await classify_intent(
        _state("please grade these class 9 science answer sheets"), router=router
    )
    assert router.json_calls == 2  # initial + one corrective retry
    assert result.intent is Intent.GRADING  # keyword heuristic caught it
    assert result.metadata["intent_source"] == "heuristic"
    assert result.metadata["intent_confidence"] == 0.3


async def test_low_confidence_routes_to_general() -> None:
    router = FakeRouter(json_sequence=[json.dumps({"intent": "grading", "confidence": 0.3})])
    result = await classify_intent(_state("hmm not sure about this"), router=router)
    assert result.intent is Intent.GENERAL  # < 0.5 confidence => safe general path
    assert result.metadata["intent_confidence"] == 0.3


async def test_empty_message_is_general() -> None:
    router = FakeRouter()
    result = await classify_intent(CopilotState(), router=router)
    assert result.intent is Intent.GENERAL
    assert router.json_calls == 0  # never called the LLM


# --- graph routing --------------------------------------------------------------


class _EmptyRetriever:
    """No-op retriever so the lesson_plan node never loads the real embedder in tests."""

    async def retrieve(self, query: str, **kwargs: object) -> list[object]:
        return []


@pytest.mark.parametrize(
    ("intent", "expected_agent", "expected_type"),
    [
        # All four specialists are live as of Phase 5; general is the inline path.
        ("grading", "grading", "grading"),
        ("lesson_plan", "lesson_plan", "lesson_plan"),
        ("wellbeing", "wellbeing", "wellbeing"),
        ("career", "career", "career"),
        ("general", "general", "general"),
    ],
)
async def test_graph_routes_each_intent(
    tmp_path: object, intent: str, expected_agent: str, expected_type: str
) -> None:
    router = FakeRouter(intent=intent, confidence=0.95, reply="Namaste! How can I help today?")
    graph = build_graph(
        router=router,
        profile_store=ProfileStore(base_path=str(tmp_path)),
        retriever=_EmptyRetriever(),  # type: ignore[arg-type]
        career_retriever=_EmptyRetriever(),  # type: ignore[arg-type]
    )

    state = await run_turn(graph, "t1", "some teacher message")

    assert state.active_agent == expected_agent
    assert state.agent_output is not None
    assert state.agent_output["type"] == expected_type
    # every path appends an assistant reply
    assert state.messages[-1].role == "assistant"


async def test_general_path_returns_text(tmp_path: object) -> None:
    router = FakeRouter(intent="general", confidence=0.95, reply="Namaste! How can I help?")
    graph = build_graph(router=router, profile_store=ProfileStore(base_path=str(tmp_path)))
    state = await run_turn(graph, "t1", "hello there")
    assert state.agent_output is not None
    assert state.agent_output["text"] == "Namaste! How can I help?"
    assert state.messages[-1].content == "Namaste! How can I help?"
    assert router.text_calls == 1  # general path made a (non-JSON) completion call


async def test_profile_loaded_into_state(tmp_path: object) -> None:
    from teacher_copilot.memory.profile import Board, TeacherProfile

    store = ProfileStore(base_path=str(tmp_path))
    await store.save(TeacherProfile(teacher_id="t1", name="Meera", board=Board.CBSE))
    router = FakeRouter(intent="general", confidence=0.95)
    graph = build_graph(router=router, profile_store=store)

    state = await run_turn(graph, "t1", "hello")
    assert state.teacher_profile is not None
    assert state.teacher_profile.name == "Meera"

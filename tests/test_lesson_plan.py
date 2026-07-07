"""Lesson plan agent tests — LLM + retriever mocked, no network, no embedder."""

from __future__ import annotations

import json
from typing import Any

from teacher_copilot.agents.lesson_plan import LessonPlanAgent
from teacher_copilot.agents.lesson_plan_models import LessonPlanRequest
from teacher_copilot.config import Settings
from teacher_copilot.memory.retrieval import RetrievedChunk
from teacher_copilot.providers.router import ProviderRouter
from teacher_copilot.providers.types import CompletionResult, Provider

PLAN_JSON = json.dumps(
    {
        "objectives": ["Explain reflection", "State the two laws of reflection"],
        "materials": ["plane mirror", "torch", "protractor"],
        "timeline": [
            {"title": "Recap", "minutes": 10, "activities": ["recall"], "teacher_notes": ""},
            {"title": "Demo", "minutes": 25, "activities": ["measure"], "teacher_notes": "pairs"},
        ],
        "assessment_ideas": ["exit ticket"],
        "homework": ["three questions"],
        "differentiation": ["scaffold for slower learners", "extension for faster learners"],
    }
)


def _chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            text="Reflection of light. Laws of reflection: angle of incidence equals angle of "
            "reflection.",
            source="sample_cbse_class8_science_light.md",
            subject="Science",
            grade="8",
            board="CBSE",
            dense_score=0.72,
            final_score=0.95,
        ),
        RetrievedChunk(
            text="The human eye focuses light onto the retina via the lens.",
            source="sample_cbse_class8_science_light.md",
            subject="Science",
            grade="8",
            board="CBSE",
            dense_score=0.58,
            final_score=0.70,
        ),
    ]


class FakeRouter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def complete(self, messages: list[Any], **kwargs: Any) -> CompletionResult:
        self.calls += 1
        return CompletionResult(text=self.text, provider=Provider.GEMINI, model="m")


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    async def retrieve(self, query: str, **kwargs: Any) -> list[RetrievedChunk]:
        return self._chunks


class FakeGeminiClient:
    """Real-protocol client for exercising the router's response cache."""

    provider = Provider.GEMINI
    default_model = "gemini-fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def complete(
        self,
        messages: list[Any],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        self.calls += 1
        return CompletionResult(text=self.text, provider=self.provider, model=model or "m")

    async def reachable(self) -> bool:
        return True


def _request() -> LessonPlanRequest:
    return LessonPlanRequest(
        topic="reflection of light", subject="Science", grade="8", board="CBSE", duration_minutes=40
    )


async def test_grounded_plan_cites_retrieved_sources() -> None:
    agent = LessonPlanAgent(router=FakeRouter(PLAN_JSON), retriever=FakeRetriever(_chunks()))
    plan = await agent.generate_plan(_request())

    assert plan.grounding == "curriculum_grounded"
    assert plan.citations
    assert plan.citations[0].source == "sample_cbse_class8_science_light.md"
    assert plan.disclaimer is None
    assert len(plan.timeline) == 2


async def test_no_retrieval_is_general_knowledge_with_disclaimer() -> None:
    agent = LessonPlanAgent(router=FakeRouter(PLAN_JSON), retriever=FakeRetriever([]))
    plan = await agent.generate_plan(_request())

    assert plan.grounding == "general_knowledge"
    assert plan.citations == []
    assert plan.disclaimer is not None


async def test_weak_retrieval_is_partial() -> None:
    weak = [
        RetrievedChunk(
            text="loosely related aside", source="x.md", dense_score=0.5, final_score=0.5
        )
    ]
    agent = LessonPlanAgent(router=FakeRouter(PLAN_JSON), retriever=FakeRetriever(weak))
    plan = await agent.generate_plan(_request())
    assert plan.grounding == "partial"


async def test_malformed_json_retries_then_degraded() -> None:
    router = FakeRouter("this is not json at all")
    agent = LessonPlanAgent(router=router, retriever=FakeRetriever([]))
    plan = await agent.generate_plan(_request())

    assert router.calls == 2  # initial + one corrective retry
    assert plan.grounding == "general_knowledge"
    assert "manually" in plan.objectives[0].lower()


async def test_identical_request_hits_router_cache() -> None:
    client = FakeGeminiClient(PLAN_JSON)
    router = ProviderRouter(
        Settings(_env_file=None),  # type: ignore[call-arg]
        clients={Provider.GEMINI: client},
    )
    agent = LessonPlanAgent(router=router, retriever=FakeRetriever(_chunks()))

    first = await agent.generate_plan(_request())
    second = await agent.generate_plan(_request())

    assert first.grounding == second.grounding == "curriculum_grounded"
    assert client.calls == 1  # second identical request served from the response cache

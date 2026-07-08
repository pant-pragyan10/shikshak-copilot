"""Career agent tests — grounded citations, general fallback, caveats always present."""

from __future__ import annotations

import json
from typing import Any

from teacher_copilot.agents.career import CareerAgent
from teacher_copilot.memory.profile import TeacherProfile
from teacher_copilot.memory.retrieval import RetrievedChunk
from teacher_copilot.orchestrator.state import CopilotState, Message
from teacher_copilot.providers.types import CompletionResult, Provider


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


def _paths() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            text="Title: Instructional Designer\nDescription: design courses and assessments.",
            source="Instructional Designer",
            dense_score=0.71,
            final_score=0.95,
        ),
        RetrievedChunk(
            text="Title: EdTech Content Developer\nDescription: write lessons for platforms.",
            source="EdTech Content Developer",
            dense_score=0.62,
            final_score=0.80,
        ),
    ]


_GROUNDED_JSON = json.dumps(
    {
        "matched_paths": [
            {
                "title": "Instructional Designer",
                "why_it_fits": "you already design lessons",
                "skills_to_build": ["ADDIE", "an authoring tool"],
                "first_steps": ["take an ID course"],
            }
        ],
        "caveats": ["transitions take time"],
    }
)


async def test_grounded_guidance_cites_dataset_paths() -> None:
    agent = CareerAgent(router=FakeRouter(_GROUNDED_JSON), retriever=FakeRetriever(_paths()))
    guidance = await agent.generate_guidance("I want to move into edtech", None)

    assert guidance.grounding == "grounded"
    assert guidance.matched_paths[0].source == "Instructional Designer"  # cites a real path
    assert guidance.disclaimer is None
    assert guidance.honest_caveats  # caveats present


async def test_empty_retrieval_is_labeled_general() -> None:
    agent = CareerAgent(router=FakeRouter(_GROUNDED_JSON), retriever=FakeRetriever([]))
    guidance = await agent.generate_guidance("what should I do next?", None)

    assert guidance.grounding == "general"
    assert guidance.disclaimer is not None  # clearly labelled as general
    # No fabricated dataset citation on the general path.
    assert all(path.source is None for path in guidance.matched_paths)


async def test_caveats_always_present_even_if_model_omits_them() -> None:
    # Model returns a rosy path with no caveats (and a salary claim we don't trust).
    rosy = json.dumps(
        {
            "matched_paths": [
                {"title": "Instructional Designer", "why_it_fits": "great pay of 20 LPA guaranteed"}
            ],
            "caveats": [],
        }
    )
    agent = CareerAgent(router=FakeRouter(rosy), retriever=FakeRetriever(_paths()))
    guidance = await agent.generate_guidance("edtech", None)

    assert guidance.honest_caveats  # our layer always attaches honest caveats


async def test_invented_title_is_not_cited_as_dataset() -> None:
    # LLM invents a title not in the retrieved set — it must not get a dataset source.
    invented = json.dumps(
        {
            "matched_paths": [
                {"title": "Chief Learning Wizard", "why_it_fits": "made up", "skills_to_build": []}
            ],
            "caveats": ["research first"],
        }
    )
    agent = CareerAgent(router=FakeRouter(invented), retriever=FakeRetriever(_paths()))
    guidance = await agent.generate_guidance("edtech", None)

    assert guidance.matched_paths[0].source is None  # not falsely attributed to the dataset


async def test_run_produces_career_output() -> None:
    profile = TeacherProfile(
        teacher_id="t", name="A", subjects=["Science"], years_experience=6
    )
    state = CopilotState(
        messages=[Message(role="user", content="I'm curious about edtech roles")],
        teacher_profile=profile,
    )
    agent = CareerAgent(router=FakeRouter(_GROUNDED_JSON), retriever=FakeRetriever(_paths()))
    updated = await agent.run(state)

    assert updated.active_agent == "career"
    assert updated.agent_output is not None
    assert updated.agent_output["type"] == "career"
    assert updated.messages[-1].role == "assistant"

"""Wellbeing agent tests — safety pre-filter, Python-computed facts, graceful fallback."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from teacher_copilot.agents.wellbeing import (
    WellbeingAgent,
    compute_signals,
    contains_distress_signal,
)
from teacher_copilot.memory.profile import TeacherProfile, WorkloadEntry
from teacher_copilot.orchestrator.state import CopilotState, Message
from teacher_copilot.providers.types import CompletionResult, Provider


class FakeRouter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def complete(self, messages: list[Any], **kwargs: Any) -> CompletionResult:
        self.calls += 1
        return CompletionResult(text=self.text, provider=Provider.GROQ, model="m")


def _state(text: str, profile: TeacherProfile | None = None) -> CopilotState:
    return CopilotState(messages=[Message(role="user", content=text)], teacher_profile=profile)


def _we(day: int, papers: int, classes: int, energy: int) -> WorkloadEntry:
    return WorkloadEntry(
        entry_date=date(2026, 7, day),
        papers_graded=papers,
        classes_taken=classes,
        self_reported_energy=energy,
    )


# --- crisis pre-filter ----------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "I want to die",
        "honestly I feel like I can't go on anymore",
        "sometimes I think everyone would be better off without me",
        "I've been thinking about ending my life",
        "I want to hurt myself",
    ],
)
def test_crisis_screen_high_recall(message: str) -> None:
    assert contains_distress_signal(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "I'm so tired after this week",
        "the workload is heavy but I'm managing",
        "I need a break from grading",
    ],
)
def test_crisis_screen_ignores_ordinary_fatigue(message: str) -> None:
    assert contains_distress_signal(message) is False


async def test_distress_triggers_handoff_without_analysis() -> None:
    router = FakeRouter("{}")
    agent = WellbeingAgent(router=router)
    state = await agent.run(_state("I feel like I can't go on anymore"))

    assert state.agent_output is not None
    assert state.agent_output["tone_flag"] == "distress_handoff"
    assert state.agent_output["resources"]  # real resources surfaced
    assert state.agent_output["observations"] == []  # NO workload analysis performed
    assert state.agent_output["practical_suggestions"] == []  # NO problem-solving
    assert state.agent_output["disclaimer"]  # always present
    assert router.calls == 0  # the LLM reflection path was NOT called


# --- Python-computed facts ------------------------------------------------------


def test_compute_signals_matches_python_math() -> None:
    entries = [_we(1, 20, 6, 2), _we(2, 10, 6, 2), _we(3, 5, 5, 3)]
    signals = compute_signals(entries)

    assert signals.days == 3
    assert signals.avg_energy == round((2 + 2 + 3) / 3, 2)
    assert signals.total_papers == 35
    assert signals.total_classes == 17
    assert signals.consecutive_high_load == 3  # all three days >= 5 classes
    assert signals.low_energy_days == 2


async def test_normal_path_uses_computed_numbers_not_llm() -> None:
    entries = [_we(1, 40, 6, 2), _we(2, 0, 5, 2)]
    profile = TeacherProfile(teacher_id="t", name="A", subjects=["Science"], workload_log=entries)
    # The LLM tries to claim a different (wrong) number; our observations ignore it.
    router = FakeRouter(
        json.dumps(
            {
                "patterns": ["you graded 999 papers"],
                "supportive_message": "You've carried a lot.",
                "practical_suggestions": ["take a short break"],
            }
        )
    )
    state = await WellbeingAgent(router=router).run(_state("feeling drained", profile))

    assert state.agent_output is not None
    observations = " ".join(state.agent_output["observations"])
    assert "40 papers" in observations  # real computed number
    assert "999" not in observations  # LLM's invented number never enters the facts
    assert state.agent_output["tone_flag"] == "elevated_workload"  # avg energy 2.0


async def test_malformed_json_falls_back_with_disclaimer() -> None:
    router = FakeRouter("not valid json")
    profile = TeacherProfile(teacher_id="t", name="A", workload_log=[_we(1, 5, 3, 4)])
    state = await WellbeingAgent(router=router).run(_state("how am I doing?", profile))

    assert router.calls == 2  # initial + one corrective retry
    assert state.agent_output is not None
    assert state.agent_output["disclaimer"]  # fallback still carries the disclaimer
    assert state.agent_output["supportive_message"]  # and a warm message
    assert state.agent_output["observations"]  # computed facts preserved


async def test_elevated_flag_on_low_energy() -> None:
    entries = [_we(d, 0, 2, 2) for d in range(1, 5)]
    signals = compute_signals(entries)
    assert signals.avg_energy <= 2.5
    from teacher_copilot.agents.wellbeing import _tone_for

    assert _tone_for(signals) == "elevated_workload"

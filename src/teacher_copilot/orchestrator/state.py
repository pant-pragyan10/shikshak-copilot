"""Shared orchestrator state.

:class:`CopilotState` is the single object threaded through the LangGraph graph
(Phase 2). Every node reads from it and returns a partial update. The field
docstrings below describe each field's *lifecycle* — who sets it and when — because
every later phase depends on this contract.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from teacher_copilot.memory.profile import TeacherProfile


class Intent(StrEnum):
    """Classified teacher intent; decides which specialist agent runs.

    ``GENERAL`` is the fallback for small-talk / unclassifiable input that no
    specialist owns (handled directly by the orchestrator in Phase 2).
    """

    GRADING = "grading"
    LESSON_PLAN = "lesson_plan"
    WELLBEING = "wellbeing"
    CAREER = "career"
    GENERAL = "general"


class Message(BaseModel):
    """A single conversation turn.

    ``role`` is one of ``user`` / ``assistant`` / ``system``. Kept as a plain model
    (rather than a langchain message) so state stays serialisable and provider-agnostic.
    """

    role: str = Field(description="Author of the message: user | assistant | system.")
    content: str = Field(description="Message text.")


class CopilotState(BaseModel):
    """The state object passed between orchestrator/agent nodes.

    Lifecycle summary (see per-field docs):
        1. Inbound request seeds ``messages`` and ``teacher_profile``.
        2. The intent node sets ``intent``.
        3. The router sets ``active_agent`` and dispatches to that agent.
        4. The agent writes ``agent_output`` and appends its reply to ``messages``.
        5. ``metadata`` accumulates cross-cutting bookkeeping throughout.
    """

    # Allow arbitrary_types so nested Pydantic models compose cleanly and future
    # phases can stash non-model helpers in metadata without friction.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    messages: list[Message] = Field(
        default_factory=list,
        description=(
            "Full conversation history. Seeded from the inbound request; each agent "
            "appends its assistant reply. Grows across turns."
        ),
    )

    intent: Intent = Field(
        default=Intent.GENERAL,
        description=(
            "Set by the intent-classifier node (Phase 2) from the latest user "
            "message. Drives routing. Defaults to GENERAL before classification."
        ),
    )

    teacher_profile: TeacherProfile | None = Field(
        default=None,
        description=(
            "The active teacher's durable profile, loaded by the memory layer at "
            "turn start. None when the teacher is not yet identified."
        ),
    )

    active_agent: str | None = Field(
        default=None,
        description=(
            "Name of the specialist agent the router dispatched to (matches "
            "BaseAgent.name). None until routing occurs. Used for tracing/telemetry."
        ),
    )

    agent_output: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Structured result produced by the active agent (e.g. grading rubric "
            "scores, lesson plan sections). Shape is agent-specific; the API layer "
            "serialises it. None until an agent runs."
        ),
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Cross-cutting bookkeeping: provider used, cache hits, token counts, "
            "retrieval citations, timing. Any node may add keys; none are removed."
        ),
    )

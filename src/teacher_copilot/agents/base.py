"""Specialist agent base class.

Every specialist (grading, lesson plan, wellbeing, career) subclasses
:class:`BaseAgent`. The orchestrator (Phase 2) treats agents uniformly: it reads
``name``/``description`` for routing and calls ``run(state)`` to execute, expecting
an updated :class:`~teacher_copilot.orchestrator.state.CopilotState` back.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from teacher_copilot.orchestrator.state import CopilotState


class BaseAgent(ABC):
    """Abstract base for all specialist agents.

    Concrete agents must define the ``name`` and ``description`` class attributes
    and implement the async ``run`` method. ``run`` is a pure state transition:
    take the current state, do work, return the (mutated or new) state — it must
    not perform I/O outside the shared provider/memory layers.
    """

    #: Stable identifier used by the router and written to ``state.active_agent``.
    name: str
    #: Human-readable capability summary, used for intent routing / docs.
    description: str

    @abstractmethod
    async def run(self, state: CopilotState) -> CopilotState:
        """Execute the agent against ``state`` and return the updated state.

        Args:
            state: The current shared orchestrator state.

        Returns:
            The updated state, typically with ``agent_output`` populated and an
            assistant message appended to ``state.messages``.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={getattr(self, 'name', '?')!r}>"

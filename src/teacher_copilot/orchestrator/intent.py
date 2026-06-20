"""Intent classification node (Phase 2).

Reads the latest user message from state and sets ``state.intent`` so the router
can dispatch to the right specialist agent.
"""

from __future__ import annotations

from teacher_copilot.orchestrator.state import CopilotState


async def classify_intent(state: CopilotState) -> CopilotState:
    """Classify the latest user message and set ``state.intent``.

    Args:
        state: Current orchestrator state (expects at least one user message).

    Returns:
        The state with ``intent`` populated.
    """
    raise NotImplementedError("Phase 2")

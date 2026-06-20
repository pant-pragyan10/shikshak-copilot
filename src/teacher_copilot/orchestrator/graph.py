"""LangGraph assembly (Phase 2).

Builds the orchestrator graph: entry -> intent classifier -> conditional route to a
specialist agent -> end. The compiled graph is what the API layer (Phase 6) invokes.
"""

from __future__ import annotations

from typing import Any


def build_graph() -> Any:
    """Build and compile the orchestrator LangGraph.

    Returns:
        A compiled LangGraph runnable operating over
        :class:`~teacher_copilot.orchestrator.state.CopilotState`.
    """
    raise NotImplementedError("Phase 2")

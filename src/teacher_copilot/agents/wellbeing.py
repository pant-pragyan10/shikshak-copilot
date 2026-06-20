"""Wellbeing agent (Phase 5).

Lightweight workload check-ins: logs signals (papers graded, hours, energy) to the
teacher profile and surfaces patterns.

NOT a therapy or diagnostic tool. It must never use clinical or diagnostic
language — it reflects workload trends, nothing more.
"""

from __future__ import annotations

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.orchestrator.state import CopilotState


class WellbeingAgent(BaseAgent):
    """Non-clinical workload check-in and pattern-surfacing agent."""

    name = "wellbeing"
    description = "Logs workload signals and surfaces patterns (non-clinical, non-diagnostic)."

    async def run(self, state: CopilotState) -> CopilotState:
        raise NotImplementedError("Phase 5")

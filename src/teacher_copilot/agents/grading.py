"""Grading agent (Phase 3).

Grades typed or scanned (image) student answers against a rubric and returns
structured feedback. Scanned answers go through the multimodal provider (Gemini).
Includes a consistency eval so repeated grading of the same answer stays stable.
"""

from __future__ import annotations

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.orchestrator.state import CopilotState


class GradingAgent(BaseAgent):
    """Rubric-based grader for typed and scanned student answers."""

    name = "grading"
    description = "Grades typed or scanned student answers against a rubric."

    async def run(self, state: CopilotState) -> CopilotState:
        raise NotImplementedError("Phase 3")

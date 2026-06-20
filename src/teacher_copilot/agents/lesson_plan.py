"""Lesson plan agent (Phase 4).

Generates CBSE/ICSE-aligned lesson plans via RAG over an ingested curriculum
corpus. Output is citation-grounded — no hallucinated syllabus content.
"""

from __future__ import annotations

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.orchestrator.state import CopilotState


class LessonPlanAgent(BaseAgent):
    """Curriculum-grounded lesson plan generator."""

    name = "lesson_plan"
    description = "Generates CBSE/ICSE-aligned, citation-grounded lesson plans via RAG."

    async def run(self, state: CopilotState) -> CopilotState:
        raise NotImplementedError("Phase 4")

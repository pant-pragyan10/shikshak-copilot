"""Career agent (Phase 5).

Suggests upskilling / pivot paths (edtech, L&D, instructional design, curriculum
consulting) via RAG over a curated Indian job-market dataset.
"""

from __future__ import annotations

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.orchestrator.state import CopilotState


class CareerAgent(BaseAgent):
    """Upskilling / pivot-path recommender grounded in an Indian job-market corpus."""

    name = "career"
    description = "Suggests upskilling and career-pivot paths via RAG over Indian job-market data."

    async def run(self, state: CopilotState) -> CopilotState:
        raise NotImplementedError("Phase 5")

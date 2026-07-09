"""Shared application context — the singletons every route needs.

Built once in :func:`create_app` and stashed on ``app.state`` so routes get them via
a single typed dependency (rather than reaching into dynamic ``app.state`` everywhere).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from fastapi import Request

from teacher_copilot.agents.career import CareerAgent
from teacher_copilot.agents.grading import GradingAgent
from teacher_copilot.agents.lesson_plan import LessonPlanAgent
from teacher_copilot.agents.wellbeing import WellbeingAgent
from teacher_copilot.api.sessions import SessionStore
from teacher_copilot.config import Settings
from teacher_copilot.memory.profile import ProfileStore
from teacher_copilot.providers.router import ProviderRouter


@dataclass
class AppContext:
    """Process-wide services shared across requests (constructed at app build time)."""

    settings: Settings
    router: ProviderRouter
    profile_store: ProfileStore
    grading_agent: GradingAgent
    lesson_agent: LessonPlanAgent
    career_agent: CareerAgent
    wellbeing_agent: WellbeingAgent
    graph: Any  # compiled LangGraph runnable
    sessions: SessionStore


def get_context(request: Request) -> AppContext:
    """FastAPI dependency: the :class:`AppContext` set on ``app.state``."""
    return cast(AppContext, request.app.state.ctx)

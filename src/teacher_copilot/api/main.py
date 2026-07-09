"""FastAPI application — the HTTP surface over the LangGraph orchestrator (Phase 6A).

``create_app`` builds the shared singletons (router, agents, compiled graph, session
store) once and exposes the orchestrator over REST + SSE. Provider/retriever overrides
can be injected for testing.

Startup stays fast: the ~2GB embedder is NOT loaded eagerly — it loads lazily on the
first RAG call (lesson plan / career). The lifespan warms cheap singletons on startup
and, on shutdown, closes the embedded Qdrant store cleanly (removing its __del__ GC
warning).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from teacher_copilot import __version__
from teacher_copilot.agents.career import CareerAgent
from teacher_copilot.agents.grading import GradingAgent
from teacher_copilot.agents.lesson_plan import LessonPlanAgent
from teacher_copilot.agents.wellbeing import WellbeingAgent
from teacher_copilot.api.context import AppContext, get_context
from teacher_copilot.api.errors import register_exception_handlers
from teacher_copilot.api.routers import chat, grading, profile, tools
from teacher_copilot.api.sessions import SessionStore
from teacher_copilot.config import get_settings
from teacher_copilot.memory.profile import ProfileStore, get_profile_store
from teacher_copilot.memory.retrieval import Retriever
from teacher_copilot.memory.vector_store import get_vector_store
from teacher_copilot.orchestrator.graph import build_graph
from teacher_copilot.providers.router import ProviderRouter, get_router

logger = logging.getLogger("teacher_copilot.api")


def create_app(
    *,
    router: ProviderRouter | None = None,
    profile_store: ProfileStore | None = None,
    retriever: Retriever | None = None,
    career_retriever: Retriever | None = None,
) -> FastAPI:
    """Build the FastAPI app. Injectable dependencies default to the shared singletons."""
    settings = get_settings()
    resolved_router = router or get_router()
    resolved_profile = profile_store or get_profile_store()

    ctx = AppContext(
        settings=settings,
        router=resolved_router,
        profile_store=resolved_profile,
        grading_agent=GradingAgent(router=resolved_router),
        lesson_agent=LessonPlanAgent(router=resolved_router, retriever=retriever),
        career_agent=CareerAgent(router=resolved_router, retriever=career_retriever),
        wellbeing_agent=WellbeingAgent(router=resolved_router, profile_store=resolved_profile),
        graph=build_graph(
            router=resolved_router,
            profile_store=resolved_profile,
            retriever=retriever,
            career_retriever=career_retriever,
        ),
        sessions=SessionStore(),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "Teacher Copilot API up (env=%s). Embedder loads lazily on first RAG call.",
            settings.env,
        )
        yield
        # Close the embedded Qdrant store only if it was actually opened (avoids
        # creating one just to close it, and keeps the __del__ GC warning away).
        if get_vector_store.cache_info().currsize:
            await get_vector_store().close()
            logger.info("closed embedded vector store")

    app = FastAPI(
        title="Teacher Copilot",
        version=__version__,
        summary="Multi-agent GenAI copilot for teachers in India.",
        lifespan=lifespan,
    )
    app.state.ctx = ctx

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    @app.get("/health", tags=["meta"])
    async def health(context: AppContext = Depends(get_context)) -> dict[str, Any]:
        """Liveness + provider health (Ollama is probed; hosted providers report config)."""
        return {
            "status": "ok",
            "version": __version__,
            "env": context.settings.env.value,
            "providers": await context.router.health(),
        }

    app.include_router(chat.router)
    app.include_router(grading.router)
    app.include_router(profile.router)
    app.include_router(tools.router)
    return app


# Module-level app for `uvicorn teacher_copilot.api.main:app`.
app = create_app()

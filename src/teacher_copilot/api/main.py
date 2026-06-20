"""FastAPI application entrypoint.

Phase 0 ships only the ``/health`` probe. Phase 6 adds the SSE chat endpoints that
drive the orchestrator and stream agent output to the Next.js frontend.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from teacher_copilot.config import get_settings

app = FastAPI(
    title="Teacher Copilot",
    version="0.0.0",
    summary="Multi-agent GenAI copilot for teachers in India.",
)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness probe. Returns 200 with the current environment."""
    settings = get_settings()
    return {"status": "ok", "env": settings.env.value}

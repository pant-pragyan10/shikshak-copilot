"""Chat endpoints: SSE streaming and a non-streaming JSON fallback.

SSE event protocol (v1) — deliberately honest about what streams today:

    event: intent        data: {"intent": "grading"}
    event: message       data: {"text": "...", "active_agent": "grading"}
    event: agent_output  data: {...structured payload...}   (only for structured agents)
    event: done          data: {"session_id": "..."}
    event: error         data: {"message": "friendly text"} (on failure)

The Phase 1 router only exposes ``complete()`` (no token streaming), so today the
whole turn is computed via ``run_turn`` and then these events are emitted in order —
we do NOT fake per-token deltas we don't have. The wire format already reserves an
``event: token`` for real streaming, so it can be dropped in later (Phase 7+) without
changing the contract or the frontend's parser.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from teacher_copilot.api.context import AppContext, get_context
from teacher_copilot.api.schemas import ChatRequest, ChatResponse
from teacher_copilot.orchestrator.graph import run_turn
from teacher_copilot.orchestrator.state import CopilotState
from teacher_copilot.providers.errors import ProviderExhaustedError

logger = logging.getLogger("teacher_copilot.api")

router = APIRouter(tags=["chat"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering so events flush promptly
}
_BUSY = "The system is busy right now (free-tier limits). Please try again in a moment."
_GENERIC = "Something went wrong. Please try again."


def _sse(event: str, data: dict[str, Any]) -> str:
    # json.dumps never emits literal newlines (they're escaped), so one data: line is safe.
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _last_assistant(state: CopilotState) -> str:
    for message in reversed(state.messages):
        if message.role == "assistant" and isinstance(message.content, str):
            return message.content
    return ""


async def _run(ctx: AppContext, req: ChatRequest) -> tuple[str, CopilotState]:
    session_id = req.session_id or uuid4().hex
    prior = await ctx.sessions.get(session_id) if req.session_id else None
    result = await run_turn(ctx.graph, req.teacher_id, req.message, prior)
    await ctx.sessions.set(session_id, result)
    return session_id, result


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest, ctx: AppContext = Depends(get_context)
) -> StreamingResponse:
    """Run a turn and stream typed SSE events (intent → message → agent_output → done)."""

    async def event_stream() -> AsyncIterator[str]:
        # Errors must be handled INSIDE the generator: once streaming starts the
        # response headers are sent, so app-level exception handlers can't run.
        try:
            session_id, result = await _run(ctx, req)
            yield _sse("intent", {"intent": result.intent})
            yield _sse(
                "message",
                {"text": _last_assistant(result), "active_agent": result.active_agent},
            )
            if result.agent_output:
                yield _sse("agent_output", result.agent_output)
            yield _sse("done", {"session_id": session_id})
        except ProviderExhaustedError:
            yield _sse("error", {"message": _BUSY})
        except Exception:
            logger.exception("chat stream failed")
            yield _sse("error", {"message": _GENERIC})

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, ctx: AppContext = Depends(get_context)) -> ChatResponse:
    """Non-streaming fallback: run a turn and return the full response as JSON."""
    session_id, result = await _run(ctx, req)
    return ChatResponse(
        session_id=session_id,
        intent=result.intent,
        active_agent=result.active_agent,
        message=_last_assistant(result),
        agent_output=result.agent_output,
    )

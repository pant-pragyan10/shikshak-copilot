"""In-memory conversation session store.

Keeps the :class:`CopilotState` for each ``session_id`` so a conversation accumulates
context across turns. Deliberately the simplest thing that works — a dict behind an
``asyncio.Lock``. The interface (``get``/``set``) is the contract, so this can be
swapped for Redis (or any shared store) in deployment without touching the routes.
"""

from __future__ import annotations

import asyncio

from teacher_copilot.orchestrator.state import CopilotState


class SessionStore:
    """Async-safe in-memory map of ``session_id`` -> :class:`CopilotState`."""

    def __init__(self) -> None:
        self._store: dict[str, CopilotState] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> CopilotState | None:
        async with self._lock:
            return self._store.get(session_id)

    async def set(self, session_id: str, state: CopilotState) -> None:
        async with self._lock:
            self._store[session_id] = state

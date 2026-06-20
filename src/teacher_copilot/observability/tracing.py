"""Langfuse tracing (Phase 7).

Initialises the Langfuse client for LLM/agent tracing. When Langfuse is not
configured (see :mod:`teacher_copilot.config`), tracing runs as a no-op so the app
behaves identically without observability infrastructure.
"""

from __future__ import annotations

from typing import Any


def init_tracing() -> Any:
    """Initialise and return the Langfuse client (or a no-op when unconfigured)."""
    raise NotImplementedError("Phase 7")

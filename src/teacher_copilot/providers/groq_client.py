"""Groq provider client (Phase 1).

Thin async wrapper over the Groq SDK for fast text inference. Only the router
imports this module.
"""

from __future__ import annotations

from teacher_copilot.providers.router import ChatMessage, CompletionResult


class GroqClient:
    """Async client for Groq chat completions."""

    async def complete(self, messages: list[ChatMessage], *, model: str) -> CompletionResult:
        """Call Groq and return a normalised completion result."""
        raise NotImplementedError("Phase 1")

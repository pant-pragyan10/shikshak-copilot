"""Ollama provider client (Phase 1).

Async wrapper over a local Ollama server (via httpx). Last-resort fallback so the
system degrades gracefully when both hosted free tiers are rate-limited. Only the
router imports this module.
"""

from __future__ import annotations

from teacher_copilot.providers.router import ChatMessage, CompletionResult


class OllamaClient:
    """Async client for a local Ollama server."""

    async def complete(self, messages: list[ChatMessage], *, model: str) -> CompletionResult:
        """Call the local Ollama server and return a normalised completion result."""
        raise NotImplementedError("Phase 1")

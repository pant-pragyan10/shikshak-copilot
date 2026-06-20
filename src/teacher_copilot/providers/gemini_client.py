"""Gemini provider client (Phase 1).

Async wrapper over the Google GenAI SDK. The multimodal-capable provider used for
scanned-answer grading (Phase 3). Only the router imports this module.
"""

from __future__ import annotations

from teacher_copilot.providers.router import ChatMessage, CompletionResult


class GeminiClient:
    """Async client for Gemini chat / multimodal completions."""

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        image_bytes: bytes | None = None,
    ) -> CompletionResult:
        """Call Gemini (optionally with an image) and return a completion result."""
        raise NotImplementedError("Phase 1")

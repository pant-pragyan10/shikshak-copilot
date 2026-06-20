"""Response cache (Phase 1).

Caches LLM completions keyed by a hash of (messages, model, params) so identical
requests avoid a network round-trip — important given free-tier rate limits.
"""

from __future__ import annotations

from teacher_copilot.providers.router import CompletionResult


class ResponseCache:
    """Key/value cache for LLM completions."""

    async def get(self, key: str) -> CompletionResult | None:
        """Return a cached completion for ``key``, or None on miss."""
        raise NotImplementedError("Phase 1")

    async def set(self, key: str, value: CompletionResult) -> None:
        """Store ``value`` under ``key``."""
        raise NotImplementedError("Phase 1")

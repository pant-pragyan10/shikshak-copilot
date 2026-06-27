"""Response cache (Phase 1).

An async-safe, dependency-free in-memory LRU cache with per-entry TTL. Caching is
opt-in (the router's ``cacheable`` flag) because only deterministic-ish calls — e.g.
regenerating the same lesson plan — should be reused; conversational calls must not.

Keys are a stable SHA-256 over the provider-agnostic request shape (messages, model,
temperature, max_tokens, json_mode), so a cached result can satisfy the request no
matter which provider originally served it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass

from teacher_copilot.providers.types import ChatMessage, CompletionResult, ImagePart, TextPart

DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h
DEFAULT_MAX_ENTRIES = 512


def _canonical_content(message: ChatMessage) -> object:
    """Deterministic, JSON-serialisable view of a message's content.

    Image bytes are represented by their SHA-256 digest so keys stay small and stable.
    """
    if isinstance(message.content, str):
        return message.content
    parts: list[dict[str, str]] = []
    for part in message.content:
        if isinstance(part, TextPart):
            parts.append({"t": "text", "v": part.text})
        elif isinstance(part, ImagePart):
            digest = hashlib.sha256(part.data).hexdigest()
            parts.append({"t": "image", "mime": part.mime_type, "sha": digest})
    return parts


@dataclass
class _Entry:
    result: CompletionResult
    expires_at: float


class ResponseCache:
    """In-memory LRU + TTL cache for LLM completions."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(
        messages: list[ChatMessage],
        *,
        model: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        """Compute a stable SHA-256 key for a request."""
        payload = {
            "messages": [{"role": m.role, "content": _canonical_content(m)} for m in messages],
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    async def get(self, key: str) -> CompletionResult | None:
        """Return a live cached result for ``key`` (marking it MRU), or None."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expires_at <= time.monotonic():
                del self._store[key]
                self._misses += 1
                return None
            self._store.move_to_end(key)
            self._hits += 1
            # Return a copy flagged as cached; never hand out the stored instance.
            return entry.result.model_copy(update={"cached": True})

    async def set(self, key: str, result: CompletionResult) -> None:
        """Store ``result`` under ``key``, evicting the LRU entry if full."""
        async with self._lock:
            self._store[key] = _Entry(result=result, expires_at=time.monotonic() + self._ttl)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def stats(self) -> dict[str, int]:
        """Return hit/miss/size counters (surfaced in tracing in Phase 7)."""
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}

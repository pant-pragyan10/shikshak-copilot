"""Qdrant vector store wrapper (Phase 2/4).

Async wrapper over the self-hosted Qdrant instance: collection management, upserts,
and similarity / hybrid search used by the RAG agents.
"""

from __future__ import annotations

from typing import Any


class VectorStore:
    """Async Qdrant client wrapper for the copilot's collections."""

    async def ensure_collection(self, name: str, *, vector_size: int) -> None:
        """Create the collection ``name`` if it does not already exist."""
        raise NotImplementedError("Phase 2")

    async def upsert(self, collection: str, points: list[dict[str, Any]]) -> None:
        """Insert or update ``points`` (id + vector + payload) in ``collection``."""
        raise NotImplementedError("Phase 4")

    async def search(
        self, collection: str, query_vector: list[float], *, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Return the ``limit`` nearest payloads to ``query_vector``."""
        raise NotImplementedError("Phase 4")

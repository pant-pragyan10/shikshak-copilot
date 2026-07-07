"""Qdrant vector store wrapper (Phase 2).

Runs Qdrant in **embedded local mode**: ``QdrantClient(path=...)`` keeps the index
in-process on disk — zero infrastructure, no server, no Docker — which is exactly
what we want for dev and CI. The tradeoff is that the embedded client is
*synchronous*, so every call here is wrapped in ``asyncio.to_thread`` to preserve an
async public interface. Swapping to a real Qdrant server later (true async client +
dashboard + horizontal scale) is a config change (``QDRANT_MODE=server``), not a
rewrite of callers.

Embedded mode file-locks its storage directory, so **only one client may exist per
path per process**. Use the process-wide :func:`get_vector_store` accessor rather
than constructing ad hoc.

This module is deliberately embedding-agnostic: it takes and returns raw vectors.
Local BGE-M3 embeddings arrive in Phase 4.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel, Field
from qdrant_client import QdrantClient, models

from teacher_copilot.config import Settings, get_settings

_T = TypeVar("_T")

_DISTANCE_MAP: dict[str, models.Distance] = {
    "cosine": models.Distance.COSINE,
    "euclid": models.Distance.EUCLID,
    "dot": models.Distance.DOT,
}


class VectorPoint(BaseModel):
    """A point to store: an id, its vector, and an arbitrary JSON payload."""

    id: str | int = Field(description="Unique point id within its collection.")
    vector: list[float] = Field(description="Embedding vector.")
    payload: dict[str, Any] = Field(default_factory=dict, description="Stored metadata.")


class SearchHit(BaseModel):
    """A single similarity-search result."""

    id: str | int = Field(description="Matched point id.")
    score: float = Field(description="Similarity score (higher = closer for cosine/dot).")
    payload: dict[str, Any] = Field(default_factory=dict, description="Stored metadata.")


def _to_filter(filters: dict[str, Any] | None) -> models.Filter | None:
    """Convert a flat ``{field: value}`` dict to a Qdrant equality filter."""
    if not filters:
        return None
    conditions = [
        models.FieldCondition(key=key, match=models.MatchValue(value=value))
        for key, value in filters.items()
    ]
    return models.Filter(must=conditions)


class VectorStore:
    """Async wrapper over an embedded Qdrant client."""

    def __init__(self, settings: Settings | None = None, *, path: str | None = None) -> None:
        resolved = path or (settings or get_settings()).qdrant_path
        self._path = resolved
        # The embedded client is backed by SQLite, which requires same-thread access.
        # Pin every call (open, ops, close) to one dedicated worker thread so the async
        # facade never trips SQLite's threading guard.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qdrant")
        self._client = self._executor.submit(lambda: QdrantClient(path=resolved)).result()
        self._closed = False

    async def _run(self, fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: fn(*args, **kwargs))

    async def collection_exists(self, name: str) -> bool:
        """True if collection ``name`` exists."""
        return await self._run(self._client.collection_exists, name)

    async def ensure_collection(
        self, name: str, *, vector_size: int, distance: str = "cosine"
    ) -> None:
        """Create collection ``name`` if it does not already exist (idempotent)."""
        if await self.collection_exists(name):
            return
        metric = _DISTANCE_MAP[distance]
        await self._run(
            self._client.create_collection,
            collection_name=name,
            vectors_config=models.VectorParams(size=vector_size, distance=metric),
        )

    async def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        """Insert or update ``points`` in ``collection``."""
        structs = [
            models.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points
        ]
        await self._run(self._client.upsert, collection_name=collection, points=structs)

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        *,
        limit: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        """Return the ``limit`` nearest points to ``query_vector``, newest API."""
        response = await self._run(
            self._client.query_points,
            collection_name=collection,
            query=query_vector,
            limit=limit,
            query_filter=_to_filter(filters),
            with_payload=True,
        )
        return [
            SearchHit(id=point.id, score=point.score, payload=point.payload or {})
            for point in response.points
        ]

    async def delete_points(self, collection: str, *, filters: dict[str, Any]) -> None:
        """Delete all points in ``collection`` matching ``filters`` (equality).

        Used for idempotent ingestion: delete a source file's existing chunks before
        re-upserting them, so re-running never leaves stale/duplicate chunks behind.
        """
        selector = _to_filter(filters)
        if selector is None:
            return
        await self._run(
            self._client.delete, collection_name=collection, points_selector=selector
        )

    async def count(self, collection: str) -> int:
        """Return the number of points in ``collection``."""
        result = await self._run(self._client.count, collection_name=collection, exact=True)
        return int(result.count)

    async def delete_collection(self, name: str) -> None:
        """Delete collection ``name`` (no error if absent)."""
        await self._run(self._client.delete_collection, name)

    async def close(self) -> None:
        """Close the embedded client and its worker thread. Idempotent."""
        if self._closed:
            return
        self._closed = True
        await self._run(self._client.close)
        self._executor.shutdown(wait=True)
        # The qdrant client's own __del__ calls close() again at GC — on whatever
        # thread the collector runs on, which trips SQLite's same-thread guard. We've
        # already closed cleanly, so neutralise that second close.
        self._client.close = lambda *a, **k: None  # type: ignore[method-assign]


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """Return the process-wide :class:`VectorStore` (single embedded client)."""
    return VectorStore(get_settings())

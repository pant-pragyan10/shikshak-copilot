"""Hybrid retrieval tests: dense+keyword merge, metadata filters, empty path."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from teacher_copilot.memory.retrieval import Retriever
from teacher_copilot.memory.vector_store import VectorPoint, VectorStore

_COLLECTION = "curriculum"


class FakeEmbedder:
    """Returns a fixed query vector so tests control dense scores exactly."""

    def __init__(self, query_vector: list[float]) -> None:
        self._q = query_vector

    async def embed_query(self, text: str) -> list[float]:
        return list(self._q)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0, 0.0] for _ in texts]


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> AsyncIterator[VectorStore]:
    vs = VectorStore(path=str(tmp_path / "qdrant"))
    try:
        yield vs
    finally:
        await vs.close()


async def test_keyword_match_ranks_above_pure_semantic(store: VectorStore) -> None:
    await store.ensure_collection(_COLLECTION, vector_size=4)
    await store.upsert(
        _COLLECTION,
        [
            # Highest dense similarity, but zero keyword overlap with the query.
            VectorPoint(
                id=1,
                vector=[1.0, 0.0, 0.0, 0.0],
                payload={"text": "gravity attracts masses toward each other", "source": "phys.md"},
            ),
            # Lower dense, but an exact keyword match — the hybrid should lift it to #1.
            VectorPoint(
                id=2,
                vector=[0.6, 0.8, 0.0, 0.0],
                payload={
                    "text": "photosynthesis happens in the chlorophyll of the leaf",
                    "source": "bio.md",
                },
            ),
            VectorPoint(
                id=3,
                vector=[0.2, 0.98, 0.0, 0.0],
                payload={"text": "the water cycle involves evaporation", "source": "geo.md"},
            ),
        ],
    )
    retriever = Retriever(FakeEmbedder([1.0, 0.0, 0.0, 0.0]), store, collection=_COLLECTION)

    hits = await retriever.retrieve("photosynthesis chlorophyll leaf", limit=6)

    assert hits[0].source == "bio.md"  # keyword boost beat the higher-dense gravity chunk
    assert hits[0].final_score >= hits[1].final_score


async def test_metadata_filter_excludes_wrong_grade(store: VectorStore) -> None:
    await store.ensure_collection(_COLLECTION, vector_size=4)
    await store.upsert(
        _COLLECTION,
        [
            VectorPoint(
                id=1, vector=[1.0, 0.0, 0.0, 0.0],
                payload={"text": "grade eight light", "source": "a.md", "grade": "8"},
            ),
            VectorPoint(
                id=2, vector=[1.0, 0.0, 0.0, 0.0],
                payload={"text": "grade nine polynomials", "source": "b.md", "grade": "9"},
            ),
        ],
    )
    retriever = Retriever(FakeEmbedder([1.0, 0.0, 0.0, 0.0]), store, collection=_COLLECTION)

    hits = await retriever.retrieve("anything", grade="8", limit=6)

    assert hits
    assert all(h.grade == "8" for h in hits)


async def test_missing_collection_returns_empty(store: VectorStore) -> None:
    retriever = Retriever(FakeEmbedder([1.0, 0.0, 0.0, 0.0]), store, collection="does_not_exist")
    assert await retriever.retrieve("light", limit=6) == []

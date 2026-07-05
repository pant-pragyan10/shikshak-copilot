"""Memory-layer tests: embedded Qdrant vector store and the JSON profile store."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio

from teacher_copilot.memory.profile import (
    Board,
    ProfileStore,
    TeacherProfile,
    WorkloadEntry,
)
from teacher_copilot.memory.vector_store import SearchHit, VectorPoint, VectorStore


@pytest_asyncio.fixture
async def store(tmp_path: object) -> AsyncIterator[VectorStore]:
    vs = VectorStore(path=str(tmp_path / "qdrant"))
    try:
        yield vs
    finally:
        await vs.close()


async def test_vector_store_roundtrip(store: VectorStore) -> None:
    await store.ensure_collection("notes", vector_size=4)
    assert await store.collection_exists("notes")
    # ensure_collection is idempotent
    await store.ensure_collection("notes", vector_size=4)

    await store.upsert(
        "notes",
        [
            VectorPoint(id=1, vector=[1.0, 0.0, 0.0, 0.0], payload={"topic": "algebra"}),
            VectorPoint(id=2, vector=[0.0, 1.0, 0.0, 0.0], payload={"topic": "biology"}),
        ],
    )

    hits = await store.search("notes", [0.9, 0.1, 0.0, 0.0], limit=1)
    assert len(hits) == 1
    assert isinstance(hits[0], SearchHit)
    assert hits[0].id == 1
    assert hits[0].payload["topic"] == "algebra"


async def test_vector_store_filtered_search(store: VectorStore) -> None:
    await store.ensure_collection("notes", vector_size=4)
    await store.upsert(
        "notes",
        [
            VectorPoint(id=1, vector=[1.0, 0.0, 0.0, 0.0], payload={"topic": "algebra"}),
            VectorPoint(id=2, vector=[0.9, 0.1, 0.0, 0.0], payload={"topic": "biology"}),
        ],
    )
    hits = await store.search("notes", [1.0, 0.0, 0.0, 0.0], limit=5, filters={"topic": "biology"})
    assert hits and all(h.payload["topic"] == "biology" for h in hits)


async def test_vector_store_delete_collection(store: VectorStore) -> None:
    await store.ensure_collection("temp", vector_size=4)
    await store.delete_collection("temp")
    assert not await store.collection_exists("temp")


def _profile() -> TeacherProfile:
    return TeacherProfile(
        teacher_id="t-42",
        name="Ravi",
        subjects=["History"],
        grades_taught=["9", "10"],
        board=Board.ICSE,
        years_experience=8,
    )


async def test_profile_store_roundtrip(tmp_path: object) -> None:
    store = ProfileStore(base_path=str(tmp_path))
    assert await store.load("t-42") is None

    await store.save(_profile())
    loaded = await store.load("t-42")
    assert loaded is not None
    assert loaded.name == "Ravi"
    assert loaded.board is Board.ICSE
    assert loaded.grades_taught == ["9", "10"]


async def test_profile_store_append_workload(tmp_path: object) -> None:
    store = ProfileStore(base_path=str(tmp_path))
    await store.save(_profile())

    entry = WorkloadEntry(
        entry_date=date(2026, 7, 5), papers_graded=30, classes_taken=4, self_reported_energy=2
    )
    updated = await store.append_workload("t-42", entry)
    assert len(updated.workload_log) == 1

    reloaded = await store.load("t-42")
    assert reloaded is not None
    assert reloaded.workload_log[0].papers_graded == 30


async def test_append_workload_unknown_teacher_raises(tmp_path: object) -> None:
    store = ProfileStore(base_path=str(tmp_path))
    entry = WorkloadEntry(entry_date=date(2026, 7, 5), self_reported_energy=3)
    with pytest.raises(ValueError, match="no profile"):
        await store.append_workload("ghost", entry)


async def test_profile_store_rejects_path_traversal(tmp_path: object) -> None:
    store = ProfileStore(base_path=str(tmp_path))
    with pytest.raises(ValueError, match="invalid teacher_id"):
        await store.load("../etc/passwd")

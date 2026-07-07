"""Ingestion tests: loader front-matter/sidecar, chunker, and idempotent ingest."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from teacher_copilot.ingestion.chunker import chunk_document, chunk_text
from teacher_copilot.ingestion.loader import LoadedDoc, load_documents
from teacher_copilot.ingestion.pipeline import ingest_path
from teacher_copilot.memory.embeddings import EMBED_DIM
from teacher_copilot.memory.vector_store import VectorStore


def _vec(text: str) -> list[float]:
    v = [0.0] * EMBED_DIM
    v[abs(hash(text)) % EMBED_DIM] = 1.0
    return v


class FakeEmbedder:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_vec(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return _vec(text)


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> AsyncIterator[VectorStore]:
    vs = VectorStore(path=str(tmp_path / "qdrant"))
    try:
        yield vs
    finally:
        await vs.close()


# --- loader ---------------------------------------------------------------------


def test_loader_parses_md_front_matter(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        "---\nsubject: Science\ngrade: 8\nboard: CBSE\n---\n\n# Light\n\nReflection...",
        encoding="utf-8",
    )
    docs = load_documents(tmp_path)
    assert len(docs) == 1
    assert docs[0].subject == "Science"
    assert docs[0].grade == "8"
    assert docs[0].board == "CBSE"
    assert "---" not in docs[0].text  # front-matter stripped from body
    assert docs[0].text.startswith("# Light")


def test_loader_reads_sidecar_json(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("Some curriculum content.", encoding="utf-8")
    (tmp_path / "b.json").write_text('{"subject": "English", "grade": "7"}', encoding="utf-8")
    docs = load_documents(tmp_path)
    assert docs[0].subject == "English"
    assert docs[0].grade == "7"


def test_loader_skips_unknown_suffixes(tmp_path: Path) -> None:
    (tmp_path / "notes.csv").write_text("a,b,c", encoding="utf-8")
    assert load_documents(tmp_path) == []


# --- chunker --------------------------------------------------------------------


def test_chunk_overlap_carries_context() -> None:
    p1 = "ALPHA " + "the quick brown fox jumps over the lazy dog again " * 3
    p2 = "BRAVO " + "the quick brown fox jumps over the lazy dog again " * 3
    p3 = "CHARLIE " + "the quick brown fox jumps over the lazy dog again " * 3
    text = "\n\n".join([p1, p2, p3])

    chunks = chunk_text(text, target_tokens=100, overlap_tokens=30)

    assert len(chunks) >= 2
    assert "ALPHA" in chunks[0] and "ALPHA" not in chunks[1]
    assert "BRAVO" in chunks[0] and "BRAVO" in chunks[1]  # overlap paragraph
    assert "CHARLIE" in chunks[1]


def test_chunk_heading_starts_new_chunk() -> None:
    section_one = "# Section One\n\n" + ("content sentence number one here. " * 20)
    section_two = "# Section Two\n\n" + ("content sentence number two here. " * 20)
    text = section_one + "\n\n" + section_two

    chunks = chunk_text(text, target_tokens=120, overlap_tokens=0)

    assert any(c.lstrip().startswith("# Section Two") for c in chunks)


def test_chunk_document_attaches_metadata() -> None:
    doc = LoadedDoc(
        text="# H\n\n" + ("word " * 500),
        source_filename="chapter.md",
        subject="Science",
        grade="8",
        board="CBSE",
    )
    chunks = chunk_document(doc, target_tokens=100, overlap_tokens=20)
    assert len(chunks) >= 2
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.source == "chapter.md" and c.subject == "Science" for c in chunks)


# --- ingestion idempotency ------------------------------------------------------


async def test_ingest_is_idempotent(tmp_path: Path, store: VectorStore) -> None:
    curriculum = tmp_path / "curriculum"
    curriculum.mkdir()
    (curriculum / "doc.md").write_text(
        "---\nsubject: Science\ngrade: 8\n---\n\n" + ("Light reflects off mirrors. " * 200),
        encoding="utf-8",
    )

    first = await ingest_path(curriculum, "curriculum", embedder=FakeEmbedder(), store=store)
    count_after_first = await store.count("curriculum")
    second = await ingest_path(curriculum, "curriculum", embedder=FakeEmbedder(), store=store)
    count_after_second = await store.count("curriculum")

    assert first > 0
    assert first == second
    assert count_after_first == count_after_second  # re-ingest replaced, no duplicates

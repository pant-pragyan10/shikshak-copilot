"""Ingestion pipeline core — testable, dependency-injected.

Kept in the package (not the script) so it can be unit-tested with a fake embedder
and a tmp-path Qdrant. The CLI in ``scripts/ingest_curriculum.py`` wires the real
embedder and vector store into these functions.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from teacher_copilot.ingestion.chunker import Chunk, chunk_document
from teacher_copilot.ingestion.loader import load_documents
from teacher_copilot.memory.embeddings import EMBED_DIM, Embedder
from teacher_copilot.memory.vector_store import VectorPoint, VectorStore

_NAMESPACE = uuid.UUID("f2b9a4d6-0c3e-4c5a-9e21-2f7c8b1a0d33")  # stable per-project

# Progress callback: (filename, chunk_count, subject, grade, board) -> None
FileCallback = Callable[[str, int, "str | None", "str | None", "str | None"], None]

__all__ = ["EMBED_DIM", "FileCallback", "ingest_path", "point_id"]


def point_id(source: str, chunk_index: int) -> str:
    """Deterministic id so re-ingesting a chunk overwrites rather than duplicates."""
    return str(uuid.uuid5(_NAMESPACE, f"{source}:{chunk_index}"))


def _payload(chunk: Chunk) -> dict[str, str | int | None]:
    return {
        "text": chunk.text,
        "source": chunk.source,
        "subject": chunk.subject,
        "grade": chunk.grade,
        "board": chunk.board,
        "chunk_index": chunk.chunk_index,
    }


async def ingest_path(
    path: str | Path,
    collection: str,
    *,
    embedder: Embedder,
    store: VectorStore,
    on_file: FileCallback | None = None,
) -> int:
    """Load, chunk, embed, and upsert every document under ``path``.

    Idempotent per file: a file's existing chunks are deleted before re-upserting, so
    re-running never leaves stale or duplicate chunks. Returns the total chunk count.
    """
    docs = load_documents(path)
    if not docs:
        return 0

    await store.ensure_collection(collection, vector_size=EMBED_DIM, distance="cosine")
    total = 0
    for doc in docs:
        chunks = chunk_document(doc)
        if not chunks:
            continue
        await store.delete_points(collection, filters={"source": doc.source_filename})
        vectors = await embedder.embed_texts([c.text for c in chunks])
        points = [
            VectorPoint(id=point_id(c.source, c.chunk_index), vector=v, payload=_payload(c))
            for c, v in zip(chunks, vectors, strict=True)
        ]
        await store.upsert(collection, points)
        total += len(points)
        if on_file is not None:
            on_file(doc.source_filename, len(points), doc.subject, doc.grade, doc.board)
    return total

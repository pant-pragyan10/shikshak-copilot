"""Load and ingest the curated career-paths dataset.

Unlike curriculum (free-text docs that get chunked), career paths are structured
records — one point per path. Each is embedded on its description + skills for
retrieval, and stores a readable blob (title, context, next steps) as the payload the
career agent grounds its guidance on. Ingestion is a clean rebuild (small static set).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from teacher_copilot.memory.embeddings import EMBED_DIM, Embedder
from teacher_copilot.memory.vector_store import VectorPoint, VectorStore

_NAMESPACE = uuid.UUID("a1c7e2b4-5d6f-4a8b-9c0d-1e2f3a4b5c6d")


class CareerPath(BaseModel):
    """One illustrative career path (synthetic, not scraped job data)."""

    title: str
    description: str
    typical_transition_from: list[str] = Field(default_factory=list)
    skills_to_build: list[str] = Field(default_factory=list)
    indian_context_notes: str = ""
    example_next_steps: list[str] = Field(default_factory=list)


def load_career_paths(path: str | Path) -> list[CareerPath]:
    """Load the career-paths dataset (the ``paths`` array of the JSON file)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [CareerPath.model_validate(item) for item in data.get("paths", [])]


def _embed_text(path: CareerPath) -> str:
    return f"{path.description} Skills: {', '.join(path.skills_to_build)}"


def _blob(path: CareerPath) -> str:
    return (
        f"Title: {path.title}\n"
        f"Description: {path.description}\n"
        f"Good transition from: {', '.join(path.typical_transition_from)}\n"
        f"Skills to build: {', '.join(path.skills_to_build)}\n"
        f"Indian context: {path.indian_context_notes}\n"
        f"Example next steps: {'; '.join(path.example_next_steps)}"
    )


async def ingest_career_paths(
    path: str | Path,
    collection: str,
    *,
    embedder: Embedder,
    store: VectorStore,
) -> int:
    """Rebuild ``collection`` from the dataset. Returns the number of paths ingested."""
    paths = load_career_paths(path)
    if not paths:
        return 0

    # Clean rebuild — the dataset is small and static, so idempotency is trivial.
    if await store.collection_exists(collection):
        await store.delete_collection(collection)
    await store.ensure_collection(collection, vector_size=EMBED_DIM, distance="cosine")

    vectors = await embedder.embed_texts([_embed_text(p) for p in paths])
    points = [
        VectorPoint(
            id=str(uuid.uuid5(_NAMESPACE, p.title)),
            vector=vector,
            payload={"text": _blob(p), "source": p.title, "title": p.title},
        )
        for p, vector in zip(paths, vectors, strict=True)
    ]
    await store.upsert(collection, points)
    return len(points)

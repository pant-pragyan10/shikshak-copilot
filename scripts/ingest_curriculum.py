#!/usr/bin/env python
"""Ingest curriculum documents into Qdrant for RAG.

Loads every supported doc under the curriculum directory, chunks it, embeds the
chunks locally with BGE-M3, and upserts them into the ``curriculum`` collection.

Idempotent: re-running replaces a file's chunks (delete-by-source, then re-upsert),
so it never leaves stale or duplicate chunks behind.

    python scripts/ingest_curriculum.py                       # uses CURRICULUM_PATH
    python scripts/ingest_curriculum.py --path data/curriculum

Embeddings run locally (first run downloads ~2GB once). No API, no cost.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from teacher_copilot.config import get_settings
from teacher_copilot.ingestion.pipeline import ingest_path
from teacher_copilot.memory.embeddings import get_embedder
from teacher_copilot.memory.vector_store import get_vector_store


def _report(
    filename: str, count: int, subject: str | None, grade: str | None, board: str | None
) -> None:
    meta = f"{subject or '-'} / grade {grade or '-'} / {board or '-'}"
    print(f"  {filename}: {count} chunks [{meta}]")


async def _main(path: Path, collection: str) -> None:
    embedder = get_embedder()
    store = get_vector_store()
    try:
        total = await ingest_path(path, collection, embedder=embedder, store=store, on_file=_report)
    finally:
        await store.close()  # clean shutdown (avoids the qdrant __del__ GC warning)
    if total == 0:
        print(f"No documents found under {path}. Nothing to ingest.")
        return
    print(f"\nIngested {total} chunks into collection '{collection}'.")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Ingest curriculum docs into Qdrant.")
    parser.add_argument("--path", type=Path, default=Path(settings.curriculum_path))
    parser.add_argument("--collection", default=settings.curriculum_collection)
    args = parser.parse_args()
    asyncio.run(_main(args.path, args.collection))


if __name__ == "__main__":
    main()

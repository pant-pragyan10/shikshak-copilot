#!/usr/bin/env python
"""Ingest the curated career-paths dataset into Qdrant for the career agent.

    python scripts/ingest_career.py
    python scripts/ingest_career.py --path data/career/career_paths.json

Rebuilds the ``career_paths`` collection. Embeddings run locally (no API, no cost).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from teacher_copilot.config import get_settings
from teacher_copilot.ingestion.career import ingest_career_paths
from teacher_copilot.memory.embeddings import get_embedder
from teacher_copilot.memory.vector_store import get_vector_store


async def _main(path: Path, collection: str) -> None:
    embedder = get_embedder()
    store = get_vector_store()
    try:
        count = await ingest_career_paths(path, collection, embedder=embedder, store=store)
    finally:
        await store.close()
    if count == 0:
        print(f"No career paths found in {path}. Nothing to ingest.")
        return
    print(f"Ingested {count} career paths into collection '{collection}'.")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Ingest career paths into Qdrant.")
    parser.add_argument("--path", type=Path, default=Path(settings.career_paths_path))
    parser.add_argument("--collection", default=settings.career_collection)
    args = parser.parse_args()
    asyncio.run(_main(args.path, args.collection))


if __name__ == "__main__":
    main()

"""Local embeddings (Phase 4).

Wraps a local ``sentence-transformers`` model (BAAI/bge-m3) to produce embeddings
without any paid API. Model loading is lazy so importing this module stays cheap.
"""

from __future__ import annotations


class Embedder:
    """Local BGE-M3 embedder."""

    #: Embedding model identifier.
    model_name = "BAAI/bge-m3"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        raise NotImplementedError("Phase 4")

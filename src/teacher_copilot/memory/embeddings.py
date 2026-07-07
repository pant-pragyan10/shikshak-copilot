"""Local embeddings (Phase 4).

Wraps ``sentence-transformers`` **BAAI/bge-m3** to produce embeddings entirely on
this machine — no embedding API, no cost, no rate limit, and (a genuine selling
point) **no student or curriculum text ever leaves the device to be embedded**.

bge-m3 is chosen deliberately: it is *multilingual*, so it handles English, Hindi,
and code-mixed Hinglish in one model — directly relevant to Indian classrooms.

Loading the model is heavy (~2GB, downloaded once from HuggingFace) and synchronous,
and `sentence-transformers` encode is CPU-bound, so both are pushed onto a thread to
keep the async interface honest. The model loads lazily on first use and is cached
process-wide via :func:`get_embedder`.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

from teacher_copilot.config import get_settings

logger = logging.getLogger("teacher_copilot.memory.embeddings")

#: bge-m3 output dimensionality.
EMBED_DIM = 1024

# BGE retrieval works best asymmetrically: queries get a short instruction prefix,
# documents do not. bge-m3 is fairly instruction-agnostic, but applying the standard
# retrieval instruction to queries (only) is the documented recommendation and costs
# nothing. Documents are embedded as-is.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class EmbedderLoadError(RuntimeError):
    """Raised when the embedding model cannot be loaded (e.g. HuggingFace unreachable)."""


class Embedder:
    """Local BGE-M3 embedder with a lazily-loaded, thread-offloaded model."""

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        *,
        query_instruction: str = BGE_QUERY_INSTRUCTION,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self.device = device or settings.embedding_device
        self._query_instruction = query_instruction
        # sentence-transformers is untyped, so the model is typed as Any.
        self._model: Any = None
        self._lock = asyncio.Lock()

    def _load(self) -> Any:
        # Import here (not at module top) so importing this module stays cheap and
        # doesn't drag in torch until embeddings are actually needed.
        from sentence_transformers import SentenceTransformer

        logger.info(
            "Loading embedding model '%s' on %s. First run downloads ~2GB from "
            "HuggingFace (one-time); subsequent runs load from cache.",
            self.model_name,
            self.device,
        )
        try:
            return SentenceTransformer(self.model_name, device=self.device)
        except Exception as exc:  # network / missing model / bad device
            raise EmbedderLoadError(
                f"Could not load embedding model '{self.model_name}'. If HuggingFace is "
                "unreachable, pre-download it once on a connected machine "
                f"(e.g. `huggingface-cli download {self.model_name}`) and retry."
            ) from exc

    async def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._load)
        return self._model

    def _encode(self, model: Any, texts: list[str]) -> list[list[float]]:
        vectors: Any = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return [vector.tolist() for vector in vectors]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed documents (no instruction prefix). Returns one vector per text."""
        if not texts:
            return []
        model = await self._ensure_model()
        return await asyncio.to_thread(self._encode, model, texts)

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single search query, applying the BGE query instruction prefix."""
        model = await self._ensure_model()
        prefixed = [self._query_instruction + text]
        vectors = await asyncio.to_thread(self._encode, model, prefixed)
        return vectors[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Return the process-wide :class:`Embedder` (model loads lazily on first use)."""
    return Embedder()

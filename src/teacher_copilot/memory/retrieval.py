"""Hybrid curriculum retrieval (Phase 4).

Two signals, merged:

1. **Dense recall** — the query is embedded with BGE-M3 and matched against the
   ``curriculum`` collection in Qdrant by cosine similarity. This finds
   semantically-related chunks even when the wording differs.
2. **Sparse re-rank** — a lightweight BM25 scorer runs over the *dense candidate
   pool* to reward exact keyword overlap (topic names, formula names, etc.), which
   pure embeddings often under-weight.

The final score is a weighted blend of the two (min-max normalised over the pool).

Honest about the limits: this is a *pragmatic* hybrid, not a production sparse index.
BM25 runs only over the candidates dense retrieval already surfaced, so a chunk that
is a perfect keyword match but a poor semantic match may never enter the pool. For a
small curriculum corpus that tradeoff is fine; a real deployment would back this with
a proper inverted index (or Qdrant's native sparse vectors).
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from pydantic import BaseModel, Field

from teacher_copilot.config import get_settings
from teacher_copilot.memory.embeddings import Embedder, get_embedder
from teacher_copilot.memory.vector_store import SearchHit, VectorStore, get_vector_store

# Blend weights. Dense leads (semantic recall is the primary signal); keyword overlap
# provides a meaningful but secondary re-rank boost.
_W_DENSE = 0.6
_W_KEYWORD = 0.4

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class RetrievedChunk(BaseModel):
    """A retrieved curriculum chunk with provenance and scores (feeds citations)."""

    text: str = Field(description="Chunk text.")
    source: str = Field(description="Source filename.")
    subject: str | None = Field(default=None)
    grade: str | None = Field(default=None)
    board: str | None = Field(default=None)
    dense_score: float = Field(description="Raw dense (cosine) similarity from Qdrant.")
    final_score: float = Field(description="Blended dense + keyword score used for ranking.")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bm25_scores(
    query: str, documents: list[str], *, k1: float = 1.5, b: float = 0.75
) -> list[float]:
    """BM25 relevance of ``query`` against each doc, scored over this pool as the corpus."""
    query_terms = set(_tokenize(query))
    if not query_terms:
        return [0.0] * len(documents)
    tokenized = [_tokenize(doc) for doc in documents]
    doc_lengths = [len(tokens) for tokens in tokenized]
    avgdl = (sum(doc_lengths) / len(doc_lengths)) if doc_lengths else 0.0
    n_docs = len(documents)

    # Document frequency per query term within the pool.
    doc_freq: dict[str, int] = {}
    for term in query_terms:
        doc_freq[term] = sum(1 for tokens in tokenized if term in tokens)

    scores: list[float] = []
    for tokens, length in zip(tokenized, doc_lengths, strict=True):
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        score = 0.0
        for term in query_terms:
            tf = counts.get(term, 0)
            if tf == 0:
                continue
            df = doc_freq[term]
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1 - b + b * (length / avgdl if avgdl else 1))
            score += idf * (tf * (k1 + 1)) / denom
        scores.append(score)
    return scores


def _min_max_normalise(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


class Retriever:
    """Hybrid dense + keyword retriever over the curriculum collection."""

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        *,
        collection: str | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = vector_store
        self._collection = collection or get_settings().curriculum_collection

    async def retrieve(
        self,
        query: str,
        *,
        subject: str | None = None,
        grade: str | None = None,
        board: str | None = None,
        limit: int = 6,
    ) -> list[RetrievedChunk]:
        """Return up to ``limit`` curriculum chunks best matching ``query``.

        Returns ``[]`` when the collection is absent or nothing matches — this drives
        the lesson-plan agent's "no curriculum found" path.
        """
        if not await self._store.collection_exists(self._collection):
            return []

        query_vector = await self._embedder.embed_query(query)
        filters = _build_filters(subject, grade, board)
        pool_size = max(limit * 3, limit)
        hits = await self._store.search(
            self._collection, query_vector, limit=pool_size, filters=filters
        )
        if not hits:
            return []

        return _merge_and_rank(query, hits, limit)


def _build_filters(
    subject: str | None, grade: str | None, board: str | None
) -> dict[str, str] | None:
    filters = {
        key: value
        for key, value in (("subject", subject), ("grade", grade), ("board", board))
        if value
    }
    return filters or None


def _merge_and_rank(query: str, hits: list[SearchHit], limit: int) -> list[RetrievedChunk]:
    texts = [str(hit.payload.get("text", "")) for hit in hits]
    dense = [hit.score for hit in hits]
    keyword = _bm25_scores(query, texts)
    dense_norm = _min_max_normalise(dense)
    keyword_norm = _min_max_normalise(keyword)

    ranked: list[RetrievedChunk] = []
    for hit, text, dense_raw, dn, kn in zip(
        hits, texts, dense, dense_norm, keyword_norm, strict=True
    ):
        final = _W_DENSE * dn + _W_KEYWORD * kn
        payload = hit.payload
        ranked.append(
            RetrievedChunk(
                text=text,
                source=str(payload.get("source", "unknown")),
                subject=payload.get("subject"),
                grade=payload.get("grade"),
                board=payload.get("board"),
                dense_score=dense_raw,
                final_score=final,
            )
        )
    ranked.sort(key=lambda c: c.final_score, reverse=True)
    return ranked[:limit]


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    """Return the process-wide curriculum :class:`Retriever`."""
    return Retriever(get_embedder(), get_vector_store())


@lru_cache(maxsize=1)
def get_career_retriever() -> Retriever:
    """Return the process-wide career-paths :class:`Retriever` (same infra, other collection)."""
    return Retriever(
        get_embedder(), get_vector_store(), collection=get_settings().career_collection
    )

"""Deterministic retrieval metrics (no LLM judge needed).

These answer "does hybrid retrieval surface the *right* curriculum source for a
teacher's question?" using the known expected source per case — recall@k and MRR. They
run with just the embedder + Qdrant, so they produce real, repeatable numbers without
spending LLM quota. (Ragas' LLM-judged context-precision/recall is layered on top in
the live script for a richer, if directional, view.)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalCaseResult(BaseModel):
    id: str
    expected_source: str
    retrieved_sources: list[str]
    hit: bool
    rank: int | None = Field(default=None, description="1-based rank of the expected source.")
    reciprocal_rank: float
    top_score: float


class RetrievalSummary(BaseModel):
    n: int
    k: int
    recall_at_k: float = Field(description="Fraction of cases where the expected source ranked.")
    mrr: float = Field(description="Mean reciprocal rank of the expected source.")


def evaluate_case(
    *,
    case_id: str,
    expected_source: str,
    retrieved_sources: list[str],
    top_score: float,
    k: int,
) -> RetrievalCaseResult:
    """Score one case: is the expected source in the top-k, and at what rank?"""
    rank: int | None = None
    for i, source in enumerate(retrieved_sources[:k], start=1):
        if source == expected_source:
            rank = i
            break
    return RetrievalCaseResult(
        id=case_id,
        expected_source=expected_source,
        retrieved_sources=retrieved_sources[:k],
        hit=rank is not None,
        rank=rank,
        reciprocal_rank=1.0 / rank if rank else 0.0,
        top_score=round(top_score, 4),
    )


def summarize_retrieval(results: list[RetrievalCaseResult], *, k: int) -> RetrievalSummary:
    n = len(results)
    if n == 0:
        return RetrievalSummary(n=0, k=k, recall_at_k=0.0, mrr=0.0)
    return RetrievalSummary(
        n=n,
        k=k,
        recall_at_k=round(sum(1 for r in results if r.hit) / n, 3),
        mrr=round(sum(r.reciprocal_rank for r in results) / n, 3),
    )

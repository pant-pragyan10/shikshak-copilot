#!/usr/bin/env python
"""Retrieval eval — LIVE (embedded Qdrant + local BGE-M3), NOT part of pytest.

Measures whether hybrid retrieval surfaces the right curriculum source for a teacher's
question. The primary, always-runnable signal is deterministic (recall@k, MRR against a
known expected source) — no LLM quota needed. An optional Ragas pass (context
precision/recall, LLM-judged) is attempted if `ragas` + a langchain judge are available.

    python scripts/ingest_curriculum.py      # once, so the collection exists
    python scripts/eval_retrieval.py --k 4

Writes a structured result to eval/results/.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from teacher_copilot.config import get_settings
from teacher_copilot.eval.dataset import load_retrieval_cases
from teacher_copilot.eval.results import make_run, save_run
from teacher_copilot.eval.retrieval_metrics import (
    RetrievalCaseResult,
    evaluate_case,
    summarize_retrieval,
)
from teacher_copilot.memory.embeddings import get_embedder
from teacher_copilot.memory.retrieval import Retriever
from teacher_copilot.memory.vector_store import get_vector_store

_DEFAULT_DATASET = Path("eval/datasets/retrieval_eval.json")

_CAVEATS = (
    "Deterministic recall@k/MRR use a small synthetic corpus with one known source per "
    "question. Ragas context metrics (if run) use a free-tier LLM judge, so treat them "
    "as directional. Expand with real curriculum for a rigorous eval."
)


async def _evaluate(dataset: Path, k: int, out_dir: Path) -> None:
    settings = get_settings()
    cases = load_retrieval_cases(dataset)
    store = get_vector_store()
    retriever = Retriever(get_embedder(), store, collection=settings.curriculum_collection)

    if not await store.collection_exists(settings.curriculum_collection):
        print(
            f"Collection '{settings.curriculum_collection}' is empty. "
            "Run `python scripts/ingest_curriculum.py` first."
        )
        await store.close()
        return

    results: list[RetrievalCaseResult] = []
    retrieved_texts: list[list[str]] = []
    for case in cases:
        chunks = await retriever.retrieve(case.question, limit=k)
        sources = [c.source for c in chunks]
        top_score = chunks[0].dense_score if chunks else 0.0
        results.append(
            evaluate_case(
                case_id=case.id,
                expected_source=case.expected_source,
                retrieved_sources=sources,
                top_score=top_score,
                k=k,
            )
        )
        retrieved_texts.append([c.text for c in chunks])

    summary = summarize_retrieval(results, k=k)

    print(f"\nRetrieval eval  (k={k}, n={summary.n})")
    print("=" * 68)
    print(f"{'case':<30}{'hit':>5}{'rank':>6}{'top_score':>12}")
    print("-" * 68)
    for r in results:
        print(f"{r.id:<30}{('yes' if r.hit else 'no'):>5}{str(r.rank or '-'):>6}{r.top_score:>12}")
    print("-" * 68)
    print(f"recall@{k} = {summary.recall_at_k}   MRR = {summary.mrr}")

    judge = "deterministic"
    ragas_scores = _try_ragas([c.question for c in cases], retrieved_texts)
    details: dict[str, Any] = {"cases": [r.model_dump() for r in results]}
    if ragas_scores is not None:
        judge = ragas_scores.pop("_judge", "ragas (free-tier LLM)")
        details["ragas"] = ragas_scores
        print(f"\nRagas (LLM-judged, directional): {ragas_scores}")

    run = make_run(
        "retrieval",
        summary=summary.model_dump(),
        details=details,
        judge=judge,
        caveats=_CAVEATS,
    )
    path = save_run(run, base_dir=out_dir)
    print(f"Wrote {path}")
    await store.close()


def _try_ragas(questions: list[str], retrieved_texts: list[list[str]]) -> dict[str, Any] | None:
    """Optional Ragas context metrics. Returns None (skipped) if unavailable.

    Ragas needs an LLM judge; the honest, free path is a langchain judge on your Groq
    key. This block is deliberately guarded — any missing dep or failure just skips it,
    leaving the deterministic metrics as the real result.
    """
    try:
        # Imported lazily and guarded — `pip install "teacher-copilot[eval]"` to enable.
        from datasets import Dataset  # type: ignore[import-not-found]
        from ragas import evaluate  # type: ignore[import-not-found]
        from ragas.metrics import context_precision  # type: ignore[import-not-found]
    except Exception:
        print("\n(ragas not installed — skipping LLM-judged context metrics. "
              'Install with: pip install "teacher-copilot[eval]")')
        return None

    try:
        ds = Dataset.from_dict(
            {
                "question": questions,
                "contexts": retrieved_texts,
                # context_precision needs a reference; use the question as a light proxy.
                "ground_truth": questions,
            }
        )
        scores = evaluate(ds, metrics=[context_precision])
        result = {k: round(float(v), 3) for k, v in scores.items() if isinstance(v, (int, float))}
        result["_judge"] = "ragas + configured LLM"
        return result
    except Exception as exc:  # judge misconfigured / quota — skip, don't fail the eval
        print(f"\n(ragas run failed — skipping: {exc})")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval eval (live embedder + Qdrant).")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--out", type=Path, default=Path("eval/results"))
    args = parser.parse_args()
    asyncio.run(_evaluate(args.dataset, args.k, args.out))


if __name__ == "__main__":
    main()

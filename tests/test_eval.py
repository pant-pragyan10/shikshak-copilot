"""Eval-logic tests — dataset loading, metric math, result serialization (no LLM/embedder)."""

from __future__ import annotations

import json
from pathlib import Path

from teacher_copilot.agents.grading_models import CriterionScore, GradedResult
from teacher_copilot.eval.dataset import load_retrieval_cases
from teacher_copilot.eval.grading_metrics import summarize_grading, summarize_grading_runs
from teacher_copilot.eval.results import load_run, make_run, save_run
from teacher_copilot.eval.retrieval_metrics import evaluate_case, summarize_retrieval


def test_load_retrieval_cases(tmp_path: Path) -> None:
    path = tmp_path / "ret.json"
    path.write_text(
        json.dumps(
            {"cases": [{"id": "a", "question": "q?", "expected_source": "src.md"}]}
        ),
        encoding="utf-8",
    )
    cases = load_retrieval_cases(path)
    assert len(cases) == 1
    assert cases[0].expected_source == "src.md"


def test_evaluate_case_hit_and_rank() -> None:
    r = evaluate_case(
        case_id="c", expected_source="b.md",
        retrieved_sources=["a.md", "b.md", "c.md"], top_score=0.7, k=4,
    )
    assert r.hit is True
    assert r.rank == 2
    assert r.reciprocal_rank == 0.5


def test_evaluate_case_miss() -> None:
    r = evaluate_case(
        case_id="c", expected_source="z.md",
        retrieved_sources=["a.md", "b.md"], top_score=0.3, k=4,
    )
    assert r.hit is False
    assert r.rank is None
    assert r.reciprocal_rank == 0.0


def test_summarize_retrieval_math() -> None:
    a = evaluate_case(case_id="1", expected_source="x", retrieved_sources=["x"], top_score=0.9, k=4)
    b = evaluate_case(
        case_id="2", expected_source="y", retrieved_sources=["a", "y"], top_score=0.5, k=4
    )
    c = evaluate_case(case_id="3", expected_source="z", retrieved_sources=["a"], top_score=0.2, k=4)
    summary = summarize_retrieval([a, b, c], k=4)
    assert summary.n == 3
    assert summary.recall_at_k == round(2 / 3, 3)
    assert summary.mrr == round((1.0 + 0.5 + 0.0) / 3, 3)


def _graded(total: int, needs_review: bool = False) -> GradedResult:
    return GradedResult(
        scores=[
            CriterionScore(
                criterion_name="Accuracy", awarded_marks=total, max_marks=5, justification="x"
            )
        ],
        total_awarded=total,
        total_max=5,
        percentage=round(100 * total / 5, 1),
        confidence=0.8,
        status="needs_review" if needs_review else "graded",
    )


def test_summarize_grading_runs_swing() -> None:
    runs = [_graded(4), _graded(4), _graded(2)]
    result = summarize_grading_runs("s1", runs, runs=3)
    assert result.max_swing == 2  # 4 - 2
    assert result.mean_total == round((4 + 4 + 2) / 3, 2)
    assert result.criterion_variance["Accuracy"] > 0


def test_summarize_grading_aggregate() -> None:
    s1 = summarize_grading_runs("s1", [_graded(4), _graded(4), _graded(4)], runs=3)
    s2 = summarize_grading_runs(
        "s2", [_graded(0, True), _graded(0, True), _graded(2)], runs=3
    )
    summary = summarize_grading([s1, s2], runs=3)
    assert summary.n_samples == 2
    assert summary.worst_swing == 2
    assert summary.needs_review_rate == round(2 / 6, 3)


def test_save_and_load_run(tmp_path: Path) -> None:
    run = make_run(
        "retrieval", summary={"recall_at_k": 1.0}, details={}, judge="deterministic", caveats="s"
    )
    path = save_run(run, base_dir=tmp_path)
    assert path.exists()
    loaded = load_run(path)
    assert loaded.eval == "retrieval"
    assert loaded.summary["recall_at_k"] == 1.0

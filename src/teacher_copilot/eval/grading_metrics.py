"""Grading-consistency metrics: how stable are marks across repeated runs?

The headline number is ``max_swing`` — the widest gap between the highest and lowest
total the same answer received across N runs. "±X marks across N runs" is exactly what
a teacher would want to know before trusting an automated grade.
"""

from __future__ import annotations

import statistics

from pydantic import BaseModel, Field

from teacher_copilot.agents.grading_models import GradedResult


class GradingSampleResult(BaseModel):
    id: str
    runs: int
    mean_total: float
    stdev_total: float
    max_swing: int = Field(description="max(total) - min(total) across runs.")
    needs_review: int
    criterion_variance: dict[str, float]


class GradingSummary(BaseModel):
    n_samples: int
    runs: int
    mean_max_swing: float = Field(description="Average per-sample mark swing across runs.")
    worst_swing: int
    needs_review_rate: float


def summarize_grading_runs(
    sample_id: str, results: list[GradedResult], *, runs: int
) -> GradingSampleResult:
    """Aggregate one sample's N grading runs into a consistency result."""
    totals = [r.total_awarded for r in results]
    per_criterion: dict[str, list[int]] = {}
    for result in results:
        for score in result.scores:
            per_criterion.setdefault(score.criterion_name, []).append(score.awarded_marks)

    variances = {
        name: round(statistics.pvariance(marks), 3) if len(marks) > 1 else 0.0
        for name, marks in per_criterion.items()
    }
    return GradingSampleResult(
        id=sample_id,
        runs=runs,
        mean_total=round(statistics.mean(totals), 2) if totals else 0.0,
        stdev_total=round(statistics.pstdev(totals), 3) if len(totals) > 1 else 0.0,
        max_swing=(max(totals) - min(totals)) if totals else 0,
        needs_review=sum(1 for r in results if r.status == "needs_review"),
        criterion_variance=variances,
    )


def summarize_grading(samples: list[GradingSampleResult], *, runs: int) -> GradingSummary:
    n = len(samples)
    if n == 0:
        return GradingSummary(
            n_samples=0, runs=runs, mean_max_swing=0.0, worst_swing=0, needs_review_rate=0.0
        )
    swings = [s.max_swing for s in samples]
    total_runs = sum(s.runs for s in samples)
    reviews = sum(s.needs_review for s in samples)
    return GradingSummary(
        n_samples=n,
        runs=runs,
        mean_max_swing=round(sum(swings) / n, 2),
        worst_swing=max(swings),
        needs_review_rate=round(reviews / total_runs, 3) if total_runs else 0.0,
    )

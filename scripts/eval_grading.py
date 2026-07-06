#!/usr/bin/env python
"""Grading consistency eval — LIVE API, costs quota (not part of pytest).

Runs each built-in sample through the grading agent N times and reports how stable
the marks are across runs: per-criterion mark variance, mean/stdev of the total, and
how often each sample was flagged needs_review. This is the "grading consistency"
metric — low variance means a teacher can trust the grade not to swing between runs.

    python scripts/eval_grading.py               # 3 runs per sample
    python scripts/eval_grading.py --runs 5
    python scripts/eval_grading.py --samples data/eval/grading_samples.json

Needs real GROQ/GEMINI keys in .env.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path
from typing import Any

from teacher_copilot.agents.grading import GradingAgent
from teacher_copilot.agents.grading_models import GradedResult, GradingRequest, Rubric
from teacher_copilot.memory.profile import TeacherProfile

_DEFAULT_SAMPLES = Path("data/eval/grading_samples.json")


def _load_samples(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _request_for(sample: dict[str, Any]) -> GradingRequest:
    rubric = Rubric.model_validate(sample["rubric"]) if sample.get("rubric") else None
    return GradingRequest(
        question=sample["question"],
        answer_text=sample["answer_text"],
        rubric=rubric,
        student_identifier=sample["id"],
    )


def _profile_for(sample: dict[str, Any]) -> TeacherProfile:
    return TeacherProfile(
        teacher_id="eval",
        name="Eval",
        subjects=[sample["subject"]],
        grades_taught=[str(sample["grade_level"])],
    )


async def _run_sample(agent: GradingAgent, sample: dict[str, Any], runs: int) -> dict[str, Any]:
    request = _request_for(sample)
    profile = _profile_for(sample)
    results: list[GradedResult] = []
    for _ in range(runs):
        results.append(await agent.grade_one(request, profile))

    totals = [r.total_awarded for r in results]
    needs_review = sum(1 for r in results if r.status == "needs_review")

    # Per-criterion marks across runs, keyed by criterion name.
    per_criterion: dict[str, list[int]] = {}
    for result in results:
        for score in result.scores:
            per_criterion.setdefault(score.criterion_name, []).append(score.awarded_marks)

    variances = {
        name: round(statistics.pvariance(marks), 3) if len(marks) > 1 else 0.0
        for name, marks in per_criterion.items()
    }
    return {
        "id": sample["id"],
        "mean_total": round(statistics.mean(totals), 2) if totals else 0.0,
        "stdev_total": round(statistics.pstdev(totals), 3) if len(totals) > 1 else 0.0,
        "needs_review": needs_review,
        "runs": runs,
        "criterion_variance": variances,
    }


def _print_report(rows: list[dict[str, Any]]) -> None:
    print("\nGrading consistency report")
    print("=" * 72)
    print(f"{'sample':<26}{'mean':>7}{'stdev':>8}{'needs_review':>14}")
    print("-" * 72)
    for row in rows:
        print(
            f"{row['id']:<26}{row['mean_total']:>7}{row['stdev_total']:>8}"
            f"{str(row['needs_review']) + '/' + str(row['runs']):>14}"
        )
    print("-" * 72)
    print("Per-criterion mark variance (lower = more consistent):")
    for row in rows:
        if row["criterion_variance"]:
            details = ", ".join(f"{k}={v}" for k, v in row["criterion_variance"].items())
            print(f"  {row['id']}: {details}")
    print()


async def _main(runs: int, samples_path: Path) -> None:
    samples = _load_samples(samples_path)
    agent = GradingAgent()
    rows = []
    for sample in samples:
        print(f"grading '{sample['id']}' x{runs} ...")
        rows.append(await _run_sample(agent, sample, runs))
    _print_report(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grading consistency eval (live API).")
    parser.add_argument("--runs", type=int, default=3, help="runs per sample (default 3)")
    parser.add_argument("--samples", type=Path, default=_DEFAULT_SAMPLES)
    args = parser.parse_args()
    asyncio.run(_main(args.runs, args.samples))


if __name__ == "__main__":
    main()

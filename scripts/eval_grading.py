#!/usr/bin/env python
"""Grading-consistency eval — LIVE API, costs quota (NOT part of pytest).

Runs each sample through the grading agent N times and measures how stable the marks
are: per-sample mark swing (max-min total), stdev, per-criterion variance, and the
needs_review rate. The headline is "±X marks across N runs" — what a teacher needs to
know before trusting an automated grade. Writes a structured result to eval/results/.

    python scripts/eval_grading.py                 # 3 runs per sample
    python scripts/eval_grading.py --runs 5

Needs a real GROQ/GEMINI key in .env.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from teacher_copilot.agents.grading import GradingAgent
from teacher_copilot.agents.grading_models import GradedResult, GradingRequest, Rubric
from teacher_copilot.config import get_settings
from teacher_copilot.eval.dataset import load_grading_samples
from teacher_copilot.eval.grading_metrics import (
    GradingSampleResult,
    summarize_grading,
    summarize_grading_runs,
)
from teacher_copilot.eval.results import make_run, save_run
from teacher_copilot.memory.profile import TeacherProfile

_DEFAULT_SAMPLES = Path("data/eval/grading_samples.json")

_CAVEATS = (
    "The grader is a free-tier LLM at temperature 0.2; scores are directional, not a "
    "psychometric measure. Small sample set. Consistency is what's measured here, not "
    "correctness against a human gold mark."
)


def _request_for(sample: dict) -> GradingRequest:
    rubric = Rubric.model_validate(sample["rubric"]) if sample.get("rubric") else None
    return GradingRequest(
        question=sample["question"],
        answer_text=sample["answer_text"],
        rubric=rubric,
        student_identifier=sample["id"],
    )


def _profile_for(sample: dict) -> TeacherProfile:
    return TeacherProfile(
        teacher_id="eval",
        name="Eval",
        subjects=[sample["subject"]],
        grades_taught=[str(sample["grade_level"])],
    )


async def _run_sample(agent: GradingAgent, sample: dict, runs: int) -> GradingSampleResult:
    request = _request_for(sample)
    profile = _profile_for(sample)
    results: list[GradedResult] = [await agent.grade_one(request, profile) for _ in range(runs)]
    return summarize_grading_runs(sample["id"], results, runs=runs)


def _print(rows: list[GradingSampleResult]) -> None:
    print("\nGrading consistency")
    print("=" * 74)
    print(f"{'sample':<26}{'mean':>7}{'stdev':>8}{'swing':>8}{'needs_review':>14}")
    print("-" * 74)
    for r in rows:
        print(
            f"{r.id:<26}{r.mean_total:>7}{r.stdev_total:>8}{r.max_swing:>8}"
            f"{str(r.needs_review) + '/' + str(r.runs):>14}"
        )
    print("-" * 74)


async def _main(runs: int, samples_path: Path, out_dir: Path) -> None:
    samples = load_grading_samples(samples_path)
    agent = GradingAgent()
    rows: list[GradingSampleResult] = []
    for sample in samples:
        print(f"grading '{sample['id']}' x{runs} ...")
        rows.append(await _run_sample(agent, sample, runs))

    _print(rows)
    summary = summarize_grading(rows, runs=runs)
    print(
        f"\nAcross {summary.n_samples} samples x{runs} runs: mean swing "
        f"{summary.mean_max_swing} marks, worst {summary.worst_swing}, "
        f"needs_review rate {summary.needs_review_rate}."
    )

    run = make_run(
        "grading",
        summary=summary.model_dump(),
        details={"samples": [r.model_dump() for r in rows]},
        judge=get_settings().groq_smart_model,
        caveats=_CAVEATS,
    )
    path = save_run(run, base_dir=out_dir)
    print(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Grading consistency eval (live API).")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--samples", type=Path, default=_DEFAULT_SAMPLES)
    parser.add_argument("--out", type=Path, default=Path("eval/results"))
    args = parser.parse_args()
    asyncio.run(_main(args.runs, args.samples, args.out))


if __name__ == "__main__":
    main()

"""Evaluation utilities (Phase 7).

Pure, testable pieces (dataset loading, metric math, result serialization) live here
so they can be unit-tested without any LLM, embedder, or Ragas dependency. The live
scripts (``scripts/eval_retrieval.py``, ``scripts/eval_grading.py``) wire these to the
real retriever / grading agent.

Datasets and committed sample results live at the repo-root ``eval/`` directory.
"""

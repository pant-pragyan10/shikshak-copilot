# Evaluation

Two things a teacher would actually ask about this product — *"does it find the right
curriculum?"* and *"will the same answer get the same grade twice?"* — measured, not
asserted. The pure metric code lives in `teacher_copilot.eval`; datasets and committed
sample results live here.

> **Honest framing.** These are directional, portfolio-grade evals on small synthetic
> datasets, run against free-tier models. They show *that evaluation is built in and
> what it currently reports* — not a rigorous benchmark. Expand the datasets and use a
> stronger judge for production claims.

## Retrieval quality — `scripts/eval_retrieval.py`

Does hybrid retrieval surface the right curriculum source for a teacher's question?
Each case in [`datasets/retrieval_eval.json`](datasets/retrieval_eval.json) has a known
expected source, so we can measure **recall@k** and **MRR** deterministically — no LLM
judge, no quota. (An optional Ragas context-precision pass, LLM-judged, layers on top if
`pip install "teacher-copilot[eval]"` and a judge are configured — treat those as
directional.)

```bash
python scripts/ingest_curriculum.py     # once, so the collection exists
python scripts/eval_retrieval.py --k 4
```

**Latest sample result** ([`results/sample_retrieval.json`](results/sample_retrieval.json),
13 questions across the 3 sample sources):

| Metric | Value |
|---|---|
| recall@4 | **1.0** |
| MRR | **1.0** |

Every question retrieved its correct source at **rank 1**. On this small, clean corpus
the hybrid dense + keyword retrieval is unambiguous; the number to watch as the corpus
grows and topics overlap is whether MRR stays near 1.

## Grading consistency — `scripts/eval_grading.py`

Grades each sample **N times** and measures how much the marks move. The headline is the
**mark swing** (max − min total across runs) — what you'd want to know before trusting an
automated grade.

```bash
python scripts/eval_grading.py --runs 3
```

**Latest sample result** ([`results/sample_grading.json`](results/sample_grading.json),
6 samples × 3 runs):

| Metric | Value |
|---|---|
| mean mark swing | **0.33 marks** |
| worst-case swing | 2 marks |
| needs_review rate | 0.167 |

Most answers scored **identically across all three runs** (0 swing). The off-topic answer
(a cell-biology answer to a Newton's-law question) was flagged `needs_review` **3/3
times** — the "never fabricate a grade" rule holding under repetition, which is the point.

## Observability

The evals measure quality; **Langfuse** makes the runtime *visible*. Every `llm.complete`
is a trace span (provider chosen, model/tier, fallbacks taken, cache hit/miss, tokens,
latency) nested under an `orchestrator.turn` span — so the free-tier routing and fallback
behaviour is inspectable, not a black box. It's a no-op unless configured; see the root
README for how to turn it on.

## Files

- `teacher_copilot/eval/` — pure, unit-tested metric + IO code (no LLM/embedder/Ragas).
- `eval/datasets/` — eval inputs (retrieval cases; grading samples are in `data/eval/`).
- `eval/results/` — run outputs (gitignored except the committed `sample_*` snapshots).

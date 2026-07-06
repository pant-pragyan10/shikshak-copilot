# Teacher Copilot

A multi-agent GenAI copilot for school teachers in India, built on LangGraph.

An **orchestrator** classifies the teacher's intent and routes to one of four
specialist agents:

- **GradingAgent** — grades typed or scanned answers against rubrics.
- **LessonPlanAgent** — RAG-grounded, CBSE/ICSE-aligned lesson plans.
- **WellbeingAgent** — lightweight workload check-ins (not a diagnostic tool).
- **CareerAgent** — upskilling / pivot suggestions over an Indian job-market corpus.

Shared infra: an **embedded Qdrant** vector store (in-process, no server/Docker), a
**teacher profile/memory** layer, and a single **provider-router**
(Groq → Gemini → Ollama) that every LLM call flows through. Embeddings run locally
(BAAI/bge-m3). Zero paid APIs.

## Quickstart

```bash
uv sync            # or: pip install -e ".[dev]"
cp .env.example .env                            # add a GROQ/GEMINI key for the LLM path
uvicorn teacher_copilot.api.main:app --reload   # GET /health -> {"status": "ok"}
python scripts/chat_demo.py                      # talk to the orchestrator in your terminal
```

No Docker required — Qdrant runs embedded on disk (`QDRANT_PATH`). Without provider
keys the orchestrator still runs, falling back to its keyword intent heuristic.

> Building this in the open, phase by phase — see [`docs/JOURNAL.md`](docs/JOURNAL.md)
> for the reasoning behind each step.

## Provider routing

Every LLM call goes through a single `ProviderRouter` (`providers/router.py`). No
other module may import a provider SDK. The router maps a **task type** to an
ordered chain of **(provider, model tier)** and walks it with retry-then-fallback:

| task_type    | used for                               | provider → model-tier chain                                   |
|--------------|----------------------------------------|---------------------------------------------------------------|
| `fast`       | intent classification, short cheap calls | Groq `GROQ_FAST_MODEL` → Gemini `GEMINI_BULK_MODEL` → Ollama |
| `smart`      | reasoning-heavy text (e.g. typed-answer feedback) | Groq `GROQ_SMART_MODEL` → Gemini `GEMINI_SMART_MODEL` → Ollama |
| `multimodal` | image inputs (scanned-answer grading)  | Gemini `GEMINI_SMART_MODEL` only (no fallback)                |
| `bulk`       | lesson-plan generation, career RAG     | Gemini `GEMINI_BULK_MODEL` → Groq `GROQ_SMART_MODEL` → Ollama  |

Model tiers are env-overridable (the env var names appear in the table); the table is expressed in
tiers, not literal model strings, so re-tiering is a config change, not a code
change. Tier defaults: `GROQ_FAST_MODEL=openai/gpt-oss-20b`,
`GROQ_SMART_MODEL=openai/gpt-oss-120b`, `GEMINI_BULK_MODEL=gemini-3.5-flash-lite`
(⚠️ verify current free-tier quota in AI Studio), `GEMINI_SMART_MODEL=gemini-3.5-flash`;
Ollama uses its client default `llama3.2:3b`. A **per-call `model=` override always
wins** over the tier. Any image in the messages forces the `multimodal` chain
regardless of the requested task type. Legacy `GROQ_MODEL` / `GEMINI_MODEL` env vars
are still honoured — mapped onto the smart tier with a startup deprecation warning.

**Fallback & retry policy.** On a `429` (rate limit) or unavailability, the router
retries the *same* provider once — honouring the server's `retry-after`, with total
sleep across the call capped at 10s — then falls back to the next provider in the
chain. An **auth error disables that provider for the rest of the process** (a bad
key never fixes itself mid-run). If the whole chain fails, it raises
`ProviderExhaustedError` carrying the per-provider reasons (the API layer turns this
into a friendly "system busy" message in Phase 6). Completions are optionally cached
(opt-in `cacheable=True`) in an in-memory LRU+TTL cache keyed by a provider-agnostic
hash of the request.

**Why this design.** Free-tier rate limits are not an edge case here — they are the
operating condition, so 429s are treated as a first-class, expected signal rather
than an error. Encoding the policy as a declarative routing table means scaling or
re-tiering the system is a table edit, not a rewrite: callers ask for a `task_type`
and never learn which provider served them.

## Orchestrator

A LangGraph `StateGraph` over `CopilotState` runs each turn: load the teacher's
profile, classify intent, then route to the matching specialist (or the general
path). `run_turn(graph, teacher_id, message, state)` is the single entry point.

```
              ┌──────────────┐     ┌─────────────────┐
   START ───▶ │ load_profile │ ──▶ │ classify_intent │
              └──────────────┘     └───────┬─────────┘
                                           │  route by state.intent
        ┌──────────────┬───────────────────┼──────────────┬───────────────┐
        ▼              ▼                    ▼              ▼               ▼
    ┌─────────┐  ┌────────────┐      ┌───────────┐   ┌────────┐   ┌──────────────────┐
    │ grading │  │ lesson_plan│      │ wellbeing │   │ career │   │ general_response │
    └────┬────┘  └─────┬──────┘      └─────┬─────┘   └───┬────┘   └────────┬─────────┘
         └─────────────┴───────────────────┴─────────────┴─────────────────┘
                                           ▼
                                          END
```

**Intent classification** asks the `fast` tier for strict JSON
(`{"intent", "confidence"}`) with few-shot examples in the Indian-teacher context.
It is defensive by construction: malformed JSON triggers one corrective retry, then
a documented keyword heuristic (confidence `0.3`); an LLM verdict below `0.5`
confidence is downgraded to the safe `general` path. A bad model response never
crashes the graph.

Grading is live (Phase 3); lesson_plan / wellbeing / career are still stubs whose
nodes return a graceful `not_implemented` output — the graph runs **end to end
today** with real intent routing and a working general chat path. Memory is wired
in: an embedded `VectorStore` (Phase 4 fills the RAG) and a JSON-file `ProfileStore`
loaded into state at the start of every turn.

## Grading agent

The flagship feature: grades typed or scanned student answers against a rubric and
returns structured, teacher-style feedback.

```
   answer (+ optional rubric)
            │
            ▼
   ┌──────────────────┐   no rubric?   ┌────────────────────┐
   │  rubric present? │ ─────────────▶ │  auto-generate it  │  (smart tier, shown
   └────────┬─────────┘                └─────────┬──────────┘   in the result)
            │ yes                                │
            ▼                                    ▼
   ┌───────────────────────────────────────────────────────┐
   │  grade against rubric                                  │
   │   • text  → smart tier                                 │
   │   • image → multimodal tier (Gemini vision)            │
   └───────────────────────┬───────────────────────────────┘
                           ▼
   ┌───────────────────────────────────────────────────────┐
   │  validate: extract_json → Pydantic → clamp to bounds   │
   │   • parse fails (x2) ─▶ needs_review (raw preserved)   │
   │   • marks over max    ─▶ clamped + flagged             │
   └───────────────────────┬───────────────────────────────┘
                           ▼
              GradedResult (scores + justifications,
              strengths, improvements, %, rubric shown)
```

**Never fabricate a grade.** If an answer is illegible, appears to answer a
different question, or the model isn't confident, the result is
`status="needs_review"` with the raw output preserved — not an invented mark. Marks
that exceed a criterion's max are clamped and the adjustment is flagged. Each
justification must cite the student's own words, and the tone is kind but honest —
it should read like a good teacher's margin notes.

**Auto-rubric, always shown.** If the teacher gives no rubric, one is generated from
the question + their profile (subject/grade) and returned in the result
(`rubric_source="auto"`), so the grade is always explainable.

**Batch design.** `grade_batch()` bounds concurrency with an `asyncio.Semaphore`
(default 3) — free-tier RPM limits make unbounded fan-out self-defeating (just 429s).
A single failed item is wrapped as a `GradingError` and never sinks the rest.

**Consistency eval** (live API, costs quota):

```bash
python scripts/eval_grading.py --runs 3      # per-criterion mark variance + needs_review
```

It grades a built-in sample set (`data/eval/grading_samples.json`) N times and
reports how stable the marks are across runs — the grading-consistency metric.

## Phase status

- [x] **Phase 0** — repo scaffold, config, shared state, base classes, `/health` ✅
- [x] **Phase 1** — provider routing + fallback + cache ✅
- [x] **Phase 2** — LangGraph orchestrator + intent routing + memory wiring ✅
- [x] **Phase 3** — grading agent (text + Gemini vision) + consistency eval ✅
- [ ] **Phase 4** — lesson plan agent + curriculum ingestion + hybrid retrieval ⬜
- [ ] **Phase 5** — wellbeing + career agents ⬜
- [ ] **Phase 6** — FastAPI SSE endpoints + Next.js frontend (`/web`) ⬜
- [ ] **Phase 7** — Langfuse tracing + Ragas evals + final docs ⬜

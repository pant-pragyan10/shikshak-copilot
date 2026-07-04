# Teacher Copilot

A multi-agent GenAI copilot for school teachers in India, built on LangGraph.

An **orchestrator** classifies the teacher's intent and routes to one of four
specialist agents:

- **GradingAgent** — grades typed or scanned answers against rubrics.
- **LessonPlanAgent** — RAG-grounded, CBSE/ICSE-aligned lesson plans.
- **WellbeingAgent** — lightweight workload check-ins (not a diagnostic tool).
- **CareerAgent** — upskilling / pivot suggestions over an Indian job-market corpus.

Shared infra: a self-hosted **Qdrant** vector store, a **teacher profile/memory**
layer, and a single **provider-router** (Groq → Gemini → Ollama) that every LLM
call flows through. Embeddings run locally (BAAI/bge-m3). Zero paid APIs.

## Quickstart

```bash
uv sync            # or: pip install -e ".[dev]"
cp .env.example .env
docker compose up -d qdrant
uvicorn teacher_copilot.api.main:app --reload   # GET /health -> {"status": "ok"}
```

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

## Phase status

- [x] **Phase 0** — repo scaffold, config, shared state, base classes, `/health` ✅
- [x] **Phase 1** — provider routing + fallback + cache ✅
- [ ] **Phase 2** — LangGraph orchestrator + intent routing + memory wiring ⬜
- [ ] **Phase 3** — grading agent (text + Gemini vision) + consistency eval ⬜
- [ ] **Phase 4** — lesson plan agent + curriculum ingestion + hybrid retrieval ⬜
- [ ] **Phase 5** — wellbeing + career agents ⬜
- [ ] **Phase 6** — FastAPI SSE endpoints + Next.js frontend (`/web`) ⬜
- [ ] **Phase 7** — Langfuse tracing + Ragas evals + final docs ⬜

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

## Provider routing

Every LLM call goes through a single `ProviderRouter` (`providers/router.py`). No
other module may import a provider SDK. The router maps a **task type** to an
ordered **provider chain** and walks it with retry-then-fallback:

| task_type    | used for                                  | provider chain              |
|--------------|-------------------------------------------|-----------------------------|
| `fast`       | chat, intent classification, wellbeing    | Groq → Gemini → Ollama      |
| `multimodal` | image inputs (scanned-answer grading)     | Gemini only (no fallback)   |
| `bulk`       | lesson-plan generation, career RAG        | Gemini → Groq → Ollama      |

Defaults: Groq `llama-3.3-70b-versatile`, Gemini `gemini-2.0-flash` (largest
free-tier daily budget of the flash models), Ollama `llama3.2:3b`. Any image in the
messages forces the `multimodal` chain regardless of the requested task type.

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

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

## Phase status

- [x] **Phase 0** — repo scaffold, config, shared state, base classes, `/health` ✅
- [ ] **Phase 1** — provider routing + fallback + cache ⬜
- [ ] **Phase 2** — LangGraph orchestrator + intent routing + memory wiring ⬜
- [ ] **Phase 3** — grading agent (text + Gemini vision) + consistency eval ⬜
- [ ] **Phase 4** — lesson plan agent + curriculum ingestion + hybrid retrieval ⬜
- [ ] **Phase 5** — wellbeing + career agents ⬜
- [ ] **Phase 6** — FastAPI SSE endpoints + Next.js frontend (`/web`) ⬜
- [ ] **Phase 7** — Langfuse tracing + Ragas evals + final docs ⬜

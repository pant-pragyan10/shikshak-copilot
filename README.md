# Teacher Copilot

**A multi-agent AI assistant for school teachers in India — grade answers (typed or
scanned), plan curriculum-grounded lessons, reflect on workload, and explore career
growth.** Built on LangGraph, served over REST + SSE, with a polished Next.js frontend.
**Zero paid APIs** — free-tier LLMs behind a resilient router, embeddings run locally.

<p>
<img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
<img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
<img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-orchestration-1C3C3C">
<img alt="Qdrant" src="https://img.shields.io/badge/Qdrant-embedded-DC244C">
<img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white">
<img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white">
<img alt="mypy strict" src="https://img.shields.io/badge/mypy-strict-2A6DB2">
<img alt="tests" src="https://img.shields.io/badge/tests-137%20passing-2ea44f">
</p>

**🔗 Live demo:** [shikshak-copilot.vercel.app](https://shikshak-copilot.vercel.app) · **API:** [pant-pragyan10-teacher-copilot-api.hf.space](https://pant-pragyan10-teacher-copilot-api.hf.space/docs) ·
**📓 [Build journal](docs/JOURNAL.md)** · **📊 [Evaluation](eval/README.md)**

<!-- Add a screenshot of the Chat screen (with a grounded lesson-plan card) at
     docs/screenshot.png and uncomment: -->
<!-- ![Teacher Copilot](docs/screenshot.png) -->

---

## What it does

Teachers in India carry a heavy, unglamorous load — stacks of papers to mark, the same
lessons to re-plan every year, real burnout, and few tools built for *them*. Four
specialist agents, each aimed at one of those problems:

| Capability | The teacher's problem it solves |
|---|---|
| 🖊️ **Grading** | Marking a class set by hand every evening. Grades typed answers *or a photo of a handwritten answer sheet* against a rubric, with per-criterion feedback. |
| 📖 **Lesson planning** | Re-planning from scratch, unsure it's syllabus-aligned. Generates a plan **grounded in retrieved curriculum, with citations** — or says honestly when it isn't. |
| 💚 **Wellbeing** | Quiet overload, no space to notice it. Reflects real workload patterns from the teacher's own logs — supportive, **never clinical**. |
| 🧭 **Career** | Feeling stuck, curious about edtech / L&D / curriculum roles. Grounded, honest guidance with real tradeoffs — no invented salaries. |

A **Chat** screen ties them together: you type naturally, an orchestrator classifies
intent and routes to the right specialist, streaming the answer back.

## Architecture

```
                        ┌───────────────────────────────────────────────┐
   Next.js frontend     │            FastAPI backend (REST + SSE)        │
   (Vercel)  ──────────▶│                                               │
   chat · tools         │   run_turn() ─▶ LangGraph orchestrator        │
                        │                    │                          │
                        │      load_profile ─┤─ classify_intent         │
                        │                    ▼ (route by intent)        │
                        │   ┌─────────┬───────────┬──────────┬────────┐ │
                        │   │ grading │ lesson_plan│ wellbeing│ career │ │
                        │   └────┬────┴─────┬──────┴────┬─────┴───┬────┘ │
                        │        └──────────┴───────────┴─────────┘      │
                        │                    │                          │
                        │        ProviderRouter (fast/smart/bulk/mm)    │
                        │        Groq → Gemini → Ollama  (+cache)        │
                        └────────────────────────────┬──────────────────┘
                                    │                 │
                        embedded Qdrant + BGE-M3      Langfuse traces
                        (local, on-disk, private)     (each call visible)
```

**Request lifecycle:** `message → load teacher profile → classify intent → route to a
specialist → (retrieve curriculum / compute workload facts) → LLM via the router →
grounded, structured response → streamed to the UI as a rich card`, with every LLM call
traced.

**Why multi-agent, not one big prompt?** Each concern has genuinely different inputs,
tools, and *failure tolerance*: grading takes an image and must never fabricate a mark;
lesson planning needs RAG and citations; wellbeing must be non-clinical and safety-first;
career needs a curated dataset. Separating them means each can be prompted, grounded, and
guard-railed for its own risk — and evaluated independently.

## Engineering decisions worth noting

- **Free-tier limits as a scaling design, not a constraint.** Every LLM call goes
  through one `ProviderRouter` with a declarative task-type → model-tier → provider
  chain (Groq → Gemini → Ollama). It retries on 429s (honouring `retry-after`), falls
  back down the chain, disables a bad-key provider for the process, and caches
  deterministic calls. Scaling up is a table edit, not a rewrite — callers never learn
  which provider served them.
- **Local embeddings = cost + privacy win.** BGE-M3 runs on-device via
  sentence-transformers — no embedding API, no per-token cost, no rate limit, and **no
  student or curriculum text leaves the machine to be embedded.** It's multilingual too
  (chosen partly for Hindi/Hinglish, on the roadmap).
- **Never fabricate — the trust throughline.** Grading returns `needs_review` (not an
  invented mark) when an answer is illegible or off-topic. Lesson plans carry a
  `grounding` flag (`curriculum_grounded` / `partial` / `general_knowledge`) and cite
  the *real* retrieved text. Career guidance won't attribute an invented job title to
  the dataset. This is the same rule everywhere.
- **Wellbeing is safety-engineered.** A high-recall crisis screen runs **first**; on a
  distress signal it does no analysis and hands off to config-driven helplines. The
  workload numbers are **computed in Python, not by the LLM** — the model only phrases
  warmth around real facts. A "not medical advice" disclaimer is always present.
- **Observability makes the routing visible.** Langfuse traces every `llm.complete`
  (provider, tier, fallbacks, cache hit/miss, tokens, latency) nested under each
  `orchestrator.turn` — so the free-tier behaviour is inspectable, not a black box. It's
  a strict no-op when unconfigured; the app runs identically without it.
- **Quality is measured, not claimed.** Retrieval and grading-consistency evals live in
  the repo with committed sample results (see below).
- **Typed and tested throughout.** `mypy --strict`, `ruff`, 137 tests (all LLM/embedder
  mocked — CI never spends a token or downloads the 2GB model).

## Observability & evaluation

**Traces (Langfuse).** Set `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (free cloud or
self-host) and every turn appears as a trace: the intent, the agent, and each provider
call with its model, fallbacks, cache status, tokens, and latency. Unset → no-op.

**Evals** ([`eval/README.md`](eval/README.md)) — real numbers from the committed sample runs:

| Eval | Result | What it means |
|---|---|---|
| Retrieval (recall@4 / MRR) | **1.0 / 1.0** | Every eval question retrieved its correct curriculum source at rank 1 |
| Grading consistency | **mean swing 0.33 marks** across 3 runs | The same answer gets essentially the same grade each time; off-topic answers refused 3/3 |

```bash
python scripts/eval_retrieval.py --k 4     # recall@k, MRR (deterministic; + optional Ragas)
python scripts/eval_grading.py --runs 3    # per-sample mark swing / needs_review rate
```

Honest framing: small synthetic datasets, free-tier judge — directional, not a
benchmark. The point is that evaluation is *built in*.

## Running locally

**Backend** (Python 3.11+, no Docker — Qdrant runs embedded on disk):

```bash
uv sync            # or: pip install -e ".[dev]"
cp .env.example .env                            # add a GROQ (and optionally GEMINI) key
python scripts/ingest_curriculum.py             # (once) index the sample curriculum
python scripts/ingest_career.py                 # (once) index the career dataset
./scripts/run_api.sh                            # http://localhost:8000  (docs at /docs)
```

**Frontend** (Node 18+):

```bash
cd web && npm install
cp .env.example .env.local                      # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                                     # http://localhost:3000
```

No provider key? The orchestrator still runs on its keyword intent heuristic. Terminal
only? `python scripts/chat_demo.py`.

## Deployment

Monorepo: **frontend → Vercel** (root dir = `web`, set `NEXT_PUBLIC_API_BASE_URL`);
**backend → Render/Railway** via the root [`Dockerfile`](Dockerfile) (built remotely — no
local Docker) with the [`render.yaml`](render.yaml) blueprint. Set `GROQ_API_KEY`,
`GEMINI_API_KEY`, and `CORS_ORIGINS` (include the Vercel URL). See
[`web/README.md`](web/README.md).

**Cold-start caveat:** local embeddings mean the ~2GB BGE-M3 model downloads on the first
lesson-plan/career request on a fresh host (slow once, or every cold start on ephemeral
free tiers). Shrink it with `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5` (~130MB, English).

## Roadmap

Deliberately deferred to keep the build focused and each phase shippable — but designed
to extend:

- **Hindi / Hinglish** — BGE-M3 was chosen partly for this; the UI and prompts are the
  remaining work.
- **Voice-to-text input** — the chat input already reserves a (disabled) mic affordance.
- **WhatsApp delivery** — meet teachers where they already are.
- **Student-facing portal** — practice + feedback loops on top of the grading agent.
- **Real token streaming** — the SSE protocol already reserves an `event: token`.
- **Auth & multi-tenant profiles** — today it's a single `teacher_id`, no login.

## Tech stack

**Backend:** Python · FastAPI · LangGraph · Pydantic v2 · Qdrant (embedded) ·
sentence-transformers (BGE-M3) · Groq / Gemini / Ollama · Langfuse · Ragas.
**Frontend:** Next.js 16 (App Router) · React 19 · TypeScript · Tailwind v4 · TanStack
Query · framer-motion.

## Build phases

- [x] **Phase 0** — scaffold, config, shared state, `/health`
- [x] **Phase 1** — provider routing + fallback + cache + model tiering
- [x] **Phase 2** — LangGraph orchestrator + intent routing + memory
- [x] **Phase 3** — grading agent (text + Gemini vision) + consistency eval
- [x] **Phase 4** — lesson-plan agent + curriculum ingestion + hybrid retrieval
- [x] **Phase 5** — wellbeing + career agents — **all four specialists live**
- [x] **Phase 6A / 6B** — FastAPI (REST + SSE) backend + Next.js frontend, **deploy-ready**
- [x] **Phase 7** — Langfuse observability + Ragas/consistency evals + docs

**Status: all agents live · observed · evaluated · deploy-ready.**

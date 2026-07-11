# Teacher Copilot

A multi-agent GenAI copilot for school teachers in India, built on LangGraph — with a
FastAPI backend (REST + SSE) and a polished Next.js frontend.

**Live demo:** _add your Vercel URL here_ · **Backend:** _add your Render/Railway URL here_

<!-- Screenshot: drop a screenshot of the Chat screen (with a grounded lesson plan
     card) at docs/screenshot.png and it renders below. -->
<!-- ![Teacher Copilot](docs/screenshot.png) -->

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

## Running locally

**Backend** (Python 3.11+, no Docker — Qdrant runs embedded on disk):

```bash
uv sync            # or: pip install -e ".[dev]"
cp .env.example .env                            # add a GROQ/GEMINI key for the LLM path
python scripts/ingest_curriculum.py             # (once) index the sample curriculum for RAG
python scripts/ingest_career.py                 # (once) index the career dataset
./scripts/run_api.sh                            # http://localhost:8000  (docs at /docs)
```

**Frontend** (Node 18+; the app is in `web/`):

```bash
cd web
npm install
cp .env.example .env.local                      # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                                     # http://localhost:3000
```

Without provider keys the orchestrator still runs (keyword intent heuristic); with a
`GROQ_API_KEY` the full LLM path works. Terminal-only? `python scripts/chat_demo.py`.

## Frontend

A production-feel Next.js 16 app (App Router, React 19, Tailwind v4) — see
[`web/`](web/). It streams the orchestrator over SSE (with a live "detected intent"
badge) and renders each agent's structured output as a rich card: score rings and
per-criterion bars for grading, a printable timeline with citations for lesson plans,
a respectful reflection (and a calm, resource-forward distress handoff) for wellbeing,
and grounded path cards for career. Light/dark themes, keyboard-navigable, responsive.

## Deployment

Monorepo: **frontend → Vercel**, **backend → Render/Railway** (both env-driven).

- **Frontend (Vercel):** import the repo, set **Root Directory = `web`**, set
  `NEXT_PUBLIC_API_BASE_URL` to the backend URL. See [`web/README.md`](web/README.md).
- **Backend (Render/Railway):** builds the root [`Dockerfile`](Dockerfile) remotely
  (Docker isn't needed on your machine). A [`render.yaml`](render.yaml) blueprint is
  included. Set env vars `GROQ_API_KEY`, `GEMINI_API_KEY`, and `CORS_ORIGINS` (must
  include your Vercel URL as a JSON list).
- **Cold-start caveat:** local embeddings mean the ~2GB BGE-M3 model downloads on the
  first lesson-plan/career request on a fresh host — that request will be slow. On a
  persistent disk it's a one-time cost; on ephemeral free tiers it recurs per cold
  start. To shrink it, set `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5` (~130MB, English).

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

## Lesson planning + RAG

Lesson plans are **grounded in retrieved curriculum and cite their sources** — the
same "never fabricate" trust rule as grading, applied to syllabus content.

```
  data/curriculum/*.md,.txt,.pdf
            │  load + parse (front-matter / sidecar json)
            ▼
       structure-aware chunking  (headings/paragraphs, ~650 tok, 80 overlap)
            │
            ▼
     BGE-M3 embeddings (LOCAL) ──▶ Qdrant "curriculum" collection   [ingest]
            ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
   "plan a lesson on reflection of light, class 8"                 [query]
            │
            ▼
   hybrid retrieve = dense (BGE-M3 cosine) + BM25 keyword re-rank
            │        + subject/grade/board metadata filters
            ▼
   grounded generate (bulk tier, cacheable) ──▶ LessonPlan + Citations + grounding
```

**Grounding is a trust signal.** A plan is `curriculum_grounded` only when retrieval
finds ≥2 chunks above a real cosine-relevance bar; one weak hit → `partial`; nothing
relevant → `general_knowledge` with an explicit disclaimer and **no citations**. It
never dresses up general knowledge as syllabus-aligned. Citations are built from the
actual retrieved text, never invented by the model.

**Hybrid search — honest about the limits.** Dense recall (BGE-M3) surfaces a
candidate pool; a lightweight BM25 scorer re-ranks it to reward exact keyword matches
(topic/formula names) that embeddings under-weight; the final score blends the two
(0.6 dense / 0.4 keyword, normalised). It's a *pragmatic* hybrid, not a production
sparse index — BM25 only sees what dense retrieval already surfaced. Fine for a small
curriculum corpus; a real deployment would add a proper inverted index or Qdrant
sparse vectors. No heavy new dependency.

**Local embeddings = cost + privacy win.** Embeddings run on-device via
`sentence-transformers` BAAI/bge-m3 (multilingual — English + Hindi + Hinglish). No
embedding API, no per-token cost, no rate limit, and **no student or curriculum text
ever leaves the machine to be embedded** — a genuine selling point for schools. First
run downloads the model (~2GB) once.

```bash
python scripts/ingest_curriculum.py     # embed + index the sample corpus into Qdrant
python scripts/chat_demo.py             # then ask for a lesson plan → grounded + cited
```

A tiny synthetic sample corpus ships in `data/curriculum/` so RAG works out of the box.

## Wellbeing agent — what it deliberately does NOT do

This is the highest-risk component in the product, so the boundaries come first:

- It is **NOT** therapy, counselling, diagnosis, or a mental-health assessment. It
  never diagnoses, never uses clinical language, never scores a person's mental
  state, and never implies it can treat anything.
- It **is** a workload-awareness and supportive-reflection tool — a caring colleague,
  not a therapist and not a cheerleader (no toxic positivity). It validates that
  teaching in India is genuinely demanding.

Two design choices enforce this:

- **Crisis pre-filter runs first.** A deliberately high-recall keyword screen checks
  the message for serious-distress / self-harm signals *before* any analysis. On a
  hit, the agent does **not** analyse or problem-solve — it responds briefly and
  warmly and hands off to real, region-appropriate professional resources
  (config-driven `WELLBEING_RESOURCES`, with a TODO to verify current India helpline
  details before real use). It never claims confidentiality, never promises outcomes,
  and always encourages reaching out to trusted people and professionals.
- **The numbers come from Python, not the LLM.** Pattern signals (avg energy over the
  last N days, consecutive high-load days, papers this week) are computed in plain
  Python from the teacher's own `WorkloadEntry` logs — so a claim like "energy 2/5
  across 5 days" is *real*, never hallucinated. The LLM only phrases warmth and
  practical, non-medical suggestions around those computed facts. A disclaimer stating
  this isn't medical advice is **always** present.

`tone_flag` is one of `routine` / `elevated_workload` / `distress_handoff`.

## Career agent

Grounded, honest guidance on career growth and pivots for Indian teachers — edtech
content, instructional design, curriculum development, L&D/corporate training,
test-prep, content creation, school leadership, assessment, teacher training.

- **Grounded in a curated dataset**, not motivational fluff and not invented job
  titles. A small, clearly-synthetic-but-realistic dataset (`data/career/career_paths.json`)
  is embedded into a `career_paths` Qdrant collection and retrieved with the same
  hybrid `Retriever` the lesson planner uses.
- **Realism guardrails**: recommend only from retrieved paths (invented titles never
  get a dataset citation), **no salary figures, no guaranteed outcomes** — framed as
  options and directions with real tradeoffs. `honest_caveats` are *always* attached,
  so nothing reads as a promise.
- **Grounding flag** like the lesson planner: `grounded` when the dataset matched,
  else clearly-labelled `general` guidance with a disclaimer.

```bash
python scripts/ingest_career.py     # embed + index the career dataset into Qdrant
```

## API (Phase 6A)

A FastAPI app exposes the orchestrator over HTTP. Startup is fast — the ~2GB embedder
loads lazily on the first RAG call, and the lifespan closes the embedded Qdrant store
cleanly on shutdown. Interactive docs at `/docs`.

```bash
./scripts/run_api.sh            # http://localhost:8000  (docs at /docs)
```

| Method & path | Purpose |
|---|---|
| `GET /health` | Liveness + per-provider health + version |
| `POST /chat/stream` | Primary endpoint — run a turn, stream typed SSE events |
| `POST /chat` | Non-streaming JSON fallback (same input) |
| `POST /grade` | Grade a typed answer → `GradedResult` |
| `POST /grade/batch` | Grade many answers (bounded concurrency) → results/errors |
| `POST /grade/image` | Multipart image upload → multimodal grade ("scan a sheet") |
| `GET /profile/{id}` · `PUT /profile/{id}` | Load / upsert a teacher profile |
| `POST /profile/{id}/workload` | Append a `WorkloadEntry` (feeds wellbeing) |
| `POST /lesson-plan` · `POST /career` | Direct structured tool endpoints (reuse the agents) |

**SSE event protocol** (`/chat/stream`, `text/event-stream`):

```
event: intent        data: {"intent": "lesson_plan"}
event: message       data: {"text": "...", "active_agent": "lesson_plan"}
event: agent_output  data: {...GradedResult | LessonPlan | WellbeingReflection | CareerGuidance...}
event: done          data: {"session_id": "..."}
event: error         data: {"message": "friendly text"}      # on failure
```

Honest note: the Phase 1 router only has `complete()` (no token streaming), so today
the turn is computed via `run_turn` and these events are emitted in order — we do
**not** fake per-token deltas. The wire format already reserves an `event: token` for
real streaming, so it drops in later without changing the contract or the frontend
parser. Errors return a consistent envelope `{"error": {"type", "message"}}`; free-tier
exhaustion becomes a friendly `503`.

```bash
# Stream a lesson plan (grounded + cited) as SSE:
curl -N -X POST localhost:8000/chat/stream -H 'Content-Type: application/json' \
  -d '{"teacher_id":"t1","message":"Plan a 40-min class 8 science lesson on reflection of light"}'

# Grade a scanned answer sheet over HTTP:
curl -X POST localhost:8000/grade/image \
  -F 'file=@answer.jpg' -F 'question=State Newton'\''s second law' \
  -F 'teacher_id=t1'
```

## Phase status

- [x] **Phase 0** — repo scaffold, config, shared state, base classes, `/health` ✅
- [x] **Phase 1** — provider routing + fallback + cache ✅
- [x] **Phase 2** — LangGraph orchestrator + intent routing + memory wiring ✅
- [x] **Phase 3** — grading agent (text + Gemini vision) + consistency eval ✅
- [x] **Phase 4** — lesson plan agent + curriculum ingestion + hybrid retrieval ✅
- [x] **Phase 5** — wellbeing + career agents ✅ — **all four specialist agents now live**
- [x] **Phase 6A** — FastAPI backend: REST + SSE over the orchestrator ✅
- [x] **Phase 6B** — Next.js frontend (`web/`) — streaming chat + rich cards, deploy-ready ✅
- [ ] **Phase 7** — Langfuse tracing + Ragas evals + final docs ⬜

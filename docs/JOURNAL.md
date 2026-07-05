# Build journal

Notes to myself as I build Shikshak Copilot, phase by phase. Mostly the *why*
behind decisions, so future-me (or anyone reading the history) can follow the
reasoning and not just the diffs.

---

## Why this exists

Teachers I know spend their evenings grading stacks of papers, rewriting the same
lesson plans every year, and quietly burning out — and there's almost no tooling
built for *them* rather than for students. I wanted to see how far I could get on a
genuinely useful assistant for school teachers in India without spending a rupee on
APIs. That constraint — **zero paid services** — ended up shaping the whole
architecture, especially the provider layer.

The plan is a small multi-agent system on LangGraph: one orchestrator that reads the
teacher's intent and routes to a specialist — grading, lesson planning, a light
well-being check-in, and career/upskilling suggestions. Shared vector store, shared
profile/memory, shared model-access layer underneath.

I'm building it in phases so each one is self-contained and testable, rather than one
big unreviewable dump.

---

## Phase 0 — scaffold

Got the skeleton in place before writing any features. The goal here was purely
*structure*: a clean `src/` package, the module tree for every subsystem I know is
coming (orchestrator, agents, memory, providers, api, observability), and correct
type signatures everywhere even where the body is just `raise NotImplementedError`.

Two things I decided to fully implement up front because everything else depends on
them:

- **Shared graph state** (`orchestrator/state.py`) — the object threaded through the
  whole graph. I documented each field's *lifecycle* (who sets it, when) because I
  know I'll forget, and a later phase reading a half-defined state object is how bugs
  creep in.
- **Config** (`config.py`) — pydantic-settings, every provider key optional so the
  app boots even with nothing configured. I want to be able to run `/health` on a
  fresh clone with no `.env`.

Decisions worth remembering: strict mypy and ruff from commit one (cheap now,
painful to retrofit later), and Qdrant self-hosted via Docker so there's no managed
vector-DB bill. Langfuse I left as a commented placeholder in the compose file — its
self-host stack is heavier than I want to pin down this early, so that's a Phase 7
problem.

Done when: `pip install -e .` works, `/health` returns `{"status": "ok"}`, and
mypy/ruff/pytest are all green.

---

## Phase 1 — provider routing

This is the heart of the "free tier only" idea. If I'm relying on Groq's and
Gemini's free tiers, then **rate limits aren't an error case — they're the normal
operating condition.** So I designed for 429s from the start instead of bolting on
retries later.

Everything funnels through one `ProviderRouter`. Hard rule I set for myself: no
module outside `providers/` is ever allowed to import a provider SDK. That keeps the
whole rest of the codebase ignorant of *which* model answered — callers just ask for
a task type and get text back.

The routing itself is a declarative table, not a pile of if/else:

- `fast` → Groq first (latency), fall back to Gemini, then local Ollama.
- `bulk` → Gemini first (bigger daily budget), then Groq, then Ollama.
- `multimodal` → Gemini only (it's the one that reads images), no text fallback.

Fallback behaviour: on a 429 or a transient failure, retry the *same* provider once
— honouring `retry-after`, with total sleep capped at 10s so a caller never hangs —
then move down the chain. Auth failures are different: a bad key won't fix itself
mid-run, so I disable that provider for the rest of the process instead of retrying
it forever. If the whole chain is exhausted, I raise a dedicated error carrying the
per-provider reasons, so the eventual API layer can turn it into a friendly "system's
busy" message.

I also added an opt-in response cache (in-memory LRU + TTL). Not every call should be
cached — a well-being chat shouldn't be — so caching is a per-call flag the agents
decide on. Regenerating the same lesson plan, yes; conversation, no.

For testing I leaned on a fake client behind the shared protocol, so the whole
fallback/retry/cache matrix is verifiable with zero network calls. That mattered — I
didn't want a test suite that quietly eats my free quota every run.

### Phase 1.1 — the model-churn tax

Shipped Phase 1 with single default models, then immediately hit the thing anyone
using these APIs hits: **model names change and get retired constantly.** Waking up
to a decommissioned model id breaking prod is not a fun way to start a day.

So I refactored the table to resolve *tiers* from config instead of hard-coding ids:
a fast and a smart tier for Groq, a bulk and a smart tier for Gemini, all
overridable by env var. Re-tiering is now a config change, not a code change. I also
split out a `smart` task type for reasoning-heavy text (grading feedback on typed
answers wants a stronger model than intent classification does).

And I made model churn a first-class error: a "model not found" response now raises a
specific error that names the model and points at the provider's deprecations page,
and the router treats it as a fall-back signal rather than crashing. Old single-model
env vars still work — they map onto the smart tier with a deprecation warning — so I
don't break my own `.env` while migrating.

---

## Phase 2 — orchestrator, intent routing, memory

Now the pieces actually talk to each other. Built the LangGraph graph that runs a
turn end to end: load the teacher's profile, classify what they want, route to the
right specialist. The specialists are still stubs, so I made their nodes return a
friendly "coming in Phase N" message instead of blowing up — the whole thing runs
today, and the general chat path already works with real keys.

A few decisions I want to remember:

- **Embedded Qdrant.** No Docker on my machine, and honestly no reason to run a
  server for dev. `QdrantClient(path=...)` keeps the index in-process on disk. The
  catch is it's synchronous and SQLite-backed, so I pinned each store to a single
  worker thread and wrapped it in an async facade. Kept a `QDRANT_MODE` switch so
  swapping to a real server later is config, not code.
- **Intent classification is defensive first.** The LLM returns strict JSON, but I
  assume it will misbehave: bad JSON gets one corrective retry, then a keyword
  heuristic takes over. And if the model says it's unsure (confidence < 0.5) I send
  the turn to the general path rather than risk dumping a "I'm exhausted" message
  into the grading agent. Misrouting a tired teacher into a grading flow is exactly
  the kind of thing that makes a product feel dumb.
- **One subtlety I hit:** the heuristic sets confidence 0.3, which is below the 0.5
  threshold — so if I ran it through the same "downgrade to general" gate, the
  keyword map would be pointless. The gate only applies to the LLM's own uncertainty;
  when the LLM fails entirely, the heuristic's keyword decision is authoritative.
- **Profiles as flat JSON files.** One file per teacher, written atomically. It's
  deliberately boring — the interface (`load`/`save`/`append_workload`) is the
  contract, and the backing store can become Postgres later without callers noticing.
- **Toolchain reality:** typing under 3.12 now, because numpy's stubs (pulled in via
  qdrant) use 3.12-only syntax. Runtime still supports 3.11.

`scripts/chat_demo.py` lets me actually talk to it from the terminal, which is the
first time this has felt like a real thing rather than plumbing.

---

## What's next

- **Phase 3** — the grading agent, including reading scanned answer sheets through
  the multimodal path, plus a consistency check so the same answer grades the same
  way twice.
- **Phase 4** — lesson plans grounded in a real CBSE/ICSE curriculum corpus, with
  citations, so it can't invent syllabus content.
- **Phase 5** — the well-being and career agents.
- **Phase 6** — FastAPI streaming endpoints and a frontend.
- **Phase 7** — tracing, evals, and polishing the docs.

Running list of principles I keep coming back to: keep the free-tier constraint
honest, keep each module single-purpose, and make the expensive/fragile things
(rate limits, model churn) explicit in the design rather than hoping they don't
happen.

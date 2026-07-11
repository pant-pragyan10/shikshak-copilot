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

## Phase 3 — the grading agent

This is the one that matters. If the copilot does anything genuinely useful for a
teacher, it's taking a chunk out of the evening spent marking papers. So I spent the
most care here, mostly on the ways it can go *wrong*.

The rule I kept coming back to: **never fabricate a grade.** A tool that confidently
marks an unreadable or off-topic answer is worse than useless — a teacher would stop
trusting it after one bad call. So the agent has a `needs_review` status it reaches
for whenever the answer is illegible, looks like it's answering a different question,
or the model just isn't sure. When parsing the model's output fails twice, it doesn't
guess — it returns needs_review and keeps the raw text so I can see what happened.

Other decisions:

- **Always show the rubric.** If the teacher doesn't give one, the agent generates a
  rubric from the question and their subject/grade, and returns it *with* the grade.
  A mark without the rubric behind it is a black box; a mark with the rubric is
  something a teacher can sanity-check in five seconds.
- **Grade against the rubric, cite the answer.** The prompt makes the model quote the
  student's own words in each justification. That's what makes it feel like margin
  notes rather than a verdict from nowhere.
- **Clamp and flag.** Models sometimes award 9 out of 3. I clamp every criterion to
  its bounds and record the adjustment rather than trusting the raw number.
- **Batch is deliberately throttled.** Marking a class set means dozens of answers,
  but the free tiers cap requests per minute. Unbounded concurrency just trips 429s
  and is slower overall, so batch grading runs through a semaphore. One answer failing
  doesn't sink the rest — it comes back as a `GradingError` in its slot.

The thing that actually bit me: Groq's strict JSON mode (`json_object`) *rejects* the
gpt-oss reasoning models with `json_validate_failed` — they like to wrap their JSON
in a sentence of reasoning. So I added `extract_json`, a tolerant extractor that pulls
the object out of prose/markdown fences, and made the Groq client quietly retry
without strict JSON mode when it hits that error. Fixed the grading path and, as a
bonus, the intent classifier that had been silently falling back to keywords since
Phase 2.

There's an eval script (`scripts/eval_grading.py`) that grades the same answers a few
times and reports how much the marks wobble between runs — consistency is the metric
a teacher would actually care about. Runs against the live API, so it's not in the
test suite.

---

## Phase 4 — lesson planning and RAG

Two things landed together here: the retrieval layer (local embeddings + hybrid
search over Qdrant) and the lesson-planning agent that sits on top of it.

The philosophy is the same one from grading, just pointed at a different failure
mode. Grading's rule was "never fabricate a mark." Here it's "never fabricate
*syllabus*." An LLM will happily invent a confident, plausible, and completely wrong
"CBSE class 8 chapter on X" — and a teacher who trusts that once won't trust it
again. So a plan carries a `grounding` flag: it's only `curriculum_grounded` when
retrieval actually found relevant chunks; if it found nothing, the plan comes back
labelled `general_knowledge` with a disclaimer and no citations. And the citations
are built from the *real retrieved text*, not from whatever the model claims — the
model grounds the content, the retrieval layer owns the provenance.

Decisions worth writing down:

- **Embeddings run locally, on purpose.** BAAI/bge-m3 via sentence-transformers. It's
  multilingual (English/Hindi/Hinglish, which is how people actually talk in these
  classrooms), but the bigger reason is that it costs nothing, has no rate limit, and
  means curriculum and student text never leave the machine to be embedded. For a
  product pitched at schools, "your data doesn't go to a third party for embedding"
  is a real selling point, not a footnote. The cost is a ~2GB one-time download and a
  heavy synchronous model, so loading and encoding both get pushed onto a thread.
- **Hybrid search, and honest about what it is.** Dense recall finds semantically
  similar chunks; a small BM25 re-rank over that candidate pool rewards exact keyword
  hits (topic and formula names) that pure embeddings tend to under-weight. It's a
  pragmatic blend, not a real sparse index — BM25 only ever sees what dense retrieval
  already pulled. I wrote that limitation into the module docstring rather than
  pretending it's more than it is. For a small corpus it's plenty.
- **The grounded/partial/general decision uses the *raw* cosine score, not the
  re-ranked one.** This one bit me while designing it: min-max normalising the final
  scores makes the best chunk in any pool look like a 1.0, even when everything in the
  pool is junk. So "did we actually find relevant curriculum?" has to be answered with
  the absolute similarity, before normalisation.
- **Lesson plans are cacheable.** Same topic, subject, grade, duration over the same
  corpus produces an identical prompt, so the Phase 1 response cache turns a repeat
  request into a free hit. This is the first place that cache really earns its keep —
  bulk generation is the expensive call.
- **Ingestion is idempotent.** Re-running deletes a file's old chunks before
  re-upserting (delete-by-source-filter), so you can edit a curriculum file and
  re-ingest without piling up duplicates.

Smoke test end to end: ingested the little synthetic sample corpus, asked for a
class-8 lesson on reflection of light, and got back a plan whose objectives and
activities were visibly lifted from the sample chapter — torch, mirror, protractor,
the two laws of reflection — with the source file cited. That's the whole point: not
a generic plan, but one grounded in *this* curriculum.

---

## Phase 5 — wellbeing and career (all four agents live)

The last two specialists. With these in, every intent the router can produce now
lands on a real agent — the graph is feature-complete.

### Wellbeing — the one I was most careful with

This is the component I'm most wary of in the whole product, and I wanted the code to
show that wariness rather than hide it. A teacher's mental health is real, and a chirpy
chatbot pretending to be a wellbeing coach is at best useless and at worst harmful. So
the module docstring leads with a blunt "what this deliberately is NOT" — not therapy,
not diagnosis, not an assessment — because being explicit about the boundary *is* the
engineering, not a disclaimer bolted on afterwards.

Two decisions carry the safety:

- **Crisis screen runs before anything else.** If the message contains a serious-
  distress or self-harm signal, the agent does not analyse workload, does not try to
  cheer anyone up, does not problem-solve. It says something brief and warm, hands off
  to real helplines, and gets out of the way. The keyword list is intentionally
  high-recall — I would much rather over-trigger a gentle "please talk to someone" than
  miss a real one. The helpline numbers live in config with a loud TODO to verify them,
  because shipping a wrong crisis number would be its own kind of harm.
- **The numbers are computed in Python, never by the model.** "Average energy 2/5 over
  five days, five days straight of 5+ classes" — those are real counts over the
  teacher's own logs. The LLM only gets to phrase the warmth and suggest non-medical,
  practical things (rest, a boundary, leaning on a colleague). I don't want it inventing
  a statistic about someone's wellbeing. A "this isn't medical advice" disclaimer is
  always present, on every path including the fallback.

The tone I aimed for is a caring colleague, not a therapist and not a motivational
poster. No toxic positivity. Teaching here is genuinely hard, and it should say so.

### Career — grounded, and honest about tradeoffs

Same trust rule as the lesson planner, different domain. An LLM asked about career
changes will happily invent job titles and confident salary figures. So the career
agent recommends only from a small curated dataset (retrieved with the same hybrid
Retriever, just a different collection), and if the model names a path that isn't in
the dataset, that recommendation simply doesn't get a citation. No salary numbers, no
guarantees — and `honest_caveats` ("transitions take time; may mean a pay change") are
always attached, even if the model forgets them. Career advice that only lists upside
is how people get burned; the caveats are non-negotiable.

Smoke tested all three paths end to end: a tired-week reflection with the real numbers
in it, a distress message that triggered the gentle handoff with helplines and no
analysis, and grounded career guidance citing actual dataset paths for a Science/Maths
teacher.

---

## Phase 6A — the API

No new brains this phase, just a front door. FastAPI over the orchestrator: a factory
that builds the router, agents, graph, and a session store once, and exposes them as
REST plus an SSE chat endpoint. Split it from the frontend (6B) on purpose — a clean,
documented, deployable API is worth having on its own, and `/docs` makes it demoable
without any UI at all.

A few things I was deliberate about:

- **Don't fake streaming I don't have.** The router only has `complete()`, so there
  are no real per-token deltas yet. I could have chunked the final string to *look*
  like streaming, but that's a lie the frontend would build on. Instead the SSE
  protocol emits honest typed events — `intent`, then the full `message`, then the
  structured `agent_output`, then `done` — and reserves an `event: token` slot so real
  streaming drops in later without changing the wire format. The docstring says this
  out loud.
- **Structured output is a first-class event.** The whole point of the agents is that
  they return real objects — a GradedResult, a LessonPlan with citations. So the stream
  carries `agent_output` as its own event, and the frontend can render a proper card
  instead of parsing prose. The text reply is for chat; the structured payload is for
  the tool UI.
- **Startup stays fast; shutdown is clean.** The embedder is ~2GB, so it must NOT load
  at boot — it loads lazily on the first RAG call, and I confirmed that in the smoke
  (the weights load *during* the first lesson-plan request, not at startup). On
  shutdown the lifespan finally closes the embedded Qdrant store, which kills the
  cross-thread `__del__` warning that's been rattling around since Phase 2 — grep for
  it in the shutdown logs now and it's gone.
- **Errors never leak.** One envelope shape everywhere, `{"error": {"type", "message"}}`.
  Free-tier exhaustion becomes a friendly 503 ("we run on free-tier limits, try again");
  an unhandled error is a generic 500 with the internals kept in the server log, not the
  response. There's a test that raises `secret_api_key=...` and asserts it never appears
  in the body.
- **The agents are almost too defensive to fail.** Amusing side effect: because every
  agent already degrades gracefully on provider errors, it's genuinely hard to make an
  endpoint 503 through the normal path — the exhaustion 503 test hits the handler
  directly rather than fighting the agents' fallbacks. Good problem to have.

The schemas in `api/schemas.py` are the contract the frontend will mirror in
TypeScript, so I kept them explicit and reused the domain models wherever the wire
shape already matched.

---

## Phase 6B — the frontend

Finally the part you can actually click. A Next.js app (App Router, React 19, Tailwind
v4) in `web/`, consuming the API from 6A. This is the piece a person sees first, so I
spent the design budget on making it feel like a real product rather than a chatbot
template.

Decisions I cared about:

- **A real identity, not default-blue-on-white.** A warm-paper background, a teal
  primary, a serif display face (Fraunces) for the wordmark and hero paired with Inter
  for the UI, and a proper dark mode. An owned SVG logo mark. The goal was "an
  education tool a teacher would trust," and generic Tailwind blue doesn't say that.
- **Structured output is the whole point, so it renders as cards, not text.** The
  backend already returns real objects — a GradedResult, a LessonPlan with citations —
  and the SSE stream carries an `agent_output` event. The frontend renders each as a
  rich card: a score ring and per-criterion bars for grading, a printable timeline with
  the curriculum sources shown for lesson plans, a respectful reflection for wellbeing.
  Parsing prose would have thrown that away.
- **The routing is visible.** When you chat, the moment the `intent` event arrives a
  little "routed to → Grading" badge appears in the side panel. It makes the multi-agent
  architecture legible instead of hidden — you can see it deciding.
- **Grade and the other tools are explicit pages, not just chat.** Phase 3 taught me
  that phrasing-based routing is fragile ("Question: … Answer: …" reads as a physics
  question, not a grading request). So each capability also has a structured page —
  Grade has a form, an image drop for scanned sheets, and a rubric builder — that hits
  the direct endpoint. Chat is the magic; the tool pages are the reliable path.
- **Wellbeing got handled with care in the UI too.** The distress handoff renders
  distinctly and calmly, with the helpline resources foregrounded and the "not a
  medical tool" disclaimer always visible — never buried under analysis. The tone of a
  screen matters as much as the tone of the words.
- **Honest about what streams.** The SSE reader mirrors the backend protocol exactly,
  including that today it's whole-message, not per-token. When real token streaming
  lands on the backend, the same events just arrive incrementally — the UI doesn't change.

I didn't touch the backend (it stayed green). One small React-19 wrinkle: its new lint
rules dislike `setState` in effects, which fought the standard SSR mount-guards — I
reworked the theme toggle to be CSS-driven and lifted the profile form into a keyed
child so its state initialises once, rather than papering over it with disables.

Deploy target is a clean monorepo split: frontend on Vercel, backend on Render/Railway
via a Dockerfile the host builds remotely (no Docker needed locally). The honest
caveat, documented loudly: local embeddings mean a ~2GB model download on the first RAG
request of a fresh host — great for privacy, rough for a free-tier cold start, so
there's a lighter-model switch for demos.

---

## What's next

- **Phase 7** — tracing, evals, and polishing the docs.

Running list of principles I keep coming back to: keep the free-tier constraint
honest, keep each module single-purpose, and make the expensive/fragile things
(rate limits, model churn) explicit in the design rather than hoping they don't
happen.

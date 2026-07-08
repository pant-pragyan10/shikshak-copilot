"""Career guidance agent (Phase 5).

Realistic, grounded guidance on career growth/pivots for Indian teachers — edtech
content, instructional design, curriculum development, L&D/corporate training,
test-prep, content creation, school leadership, assessment, teacher training. Grounded
in a curated (synthetic-but-realistic) dataset, retrieved with the same hybrid
Retriever the lesson planner uses.

Guardrails: recommend only from retrieved dataset paths (no invented job titles), no
salary figures, no guaranteed outcomes — frame as options and directions with honest
tradeoffs. When retrieval finds nothing, guidance is clearly labelled ``general`` with
a disclaimer, never dressed up as dataset-grounded. ``honest_caveats`` is always
present so nothing reads as a promise.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, ValidationError

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.agents.career_models import CareerGrounding, CareerGuidance, MatchedPath
from teacher_copilot.memory.profile import TeacherProfile
from teacher_copilot.memory.retrieval import RetrievedChunk, Retriever, get_career_retriever
from teacher_copilot.orchestrator.state import CopilotState, Message
from teacher_copilot.providers.errors import ProviderError
from teacher_copilot.providers.json_utils import JSONExtractionError, extract_json
from teacher_copilot.providers.router import ChatMessage, ProviderRouter, get_router

logger = logging.getLogger("teacher_copilot.agents.career")

_DENSE_RELEVANCE = 0.40  # career descriptions are short; a slightly lower bar than lessons
_MAX_PATHS = 4

_DEFAULT_CAVEATS = [
    "Career moves take time — a transition can mean starting in a smaller role or a "
    "temporary change in pay.",
    "These are directions to explore, not guarantees. Talk to people already doing the "
    "work before you commit.",
]

_GENERAL_DISCLAIMER = (
    "No specific matches were found in the career dataset, so this is general guidance "
    "rather than grounded in curated paths. Treat it as directions to research further."
)

_SCHEMA = (
    '{"matched_paths": [{"title": "...", "why_it_fits": "...", '
    '"skills_to_build": ["..."], "first_steps": ["..."]}], '
    '"caveats": ["honest tradeoffs"]}'
)

_GROUNDED_SYSTEM = (
    "You are a grounded, honest career mentor for a school teacher in India. Recommend "
    "ONLY from the career paths given as context — do not invent job titles. Do NOT "
    "invent salary figures and do NOT promise outcomes or guarantees. Frame everything "
    "as options and directions with real tradeoffs, in the Indian job-market context. "
    "Use the teacher's subjects and experience to explain why each path fits.\n\n"
    "Output ONLY this JSON, no prose:\n" + _SCHEMA
)

_GENERAL_SYSTEM = (
    "You are a grounded, honest career mentor for a school teacher in India. No curated "
    "dataset matches were found, so give honest, general directions for teacher career "
    "growth (edtech, instructional design, curriculum, L&D, test-prep, leadership). Do "
    "NOT invent salary figures or guarantees, and make clear these are general "
    "suggestions to research.\n\n"
    "Output ONLY this JSON, no prose:\n" + _SCHEMA
)


class _LLMMatchedPath(BaseModel):
    title: str = ""
    why_it_fits: str = ""
    skills_to_build: list[str] = Field(default_factory=list)
    first_steps: list[str] = Field(default_factory=list)


class _LLMGuidance(BaseModel):
    matched_paths: list[_LLMMatchedPath] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class CareerAgent(BaseAgent):
    """Upskilling / pivot-path recommender grounded in a curated career dataset."""

    name = "career"
    description = "Suggests upskilling and career-pivot paths via RAG over Indian job-market data."

    def __init__(
        self, *, router: ProviderRouter | None = None, retriever: Retriever | None = None
    ) -> None:
        self._router = router
        self._retriever = retriever

    @property
    def router(self) -> ProviderRouter:
        return self._router if self._router is not None else get_router()

    @property
    def retriever(self) -> Retriever:
        return self._retriever if self._retriever is not None else get_career_retriever()

    async def run(self, state: CopilotState) -> CopilotState:
        """Produce grounded career guidance for the latest turn."""
        state.active_agent = self.name
        interest = _last_user_text(state) or ""
        try:
            guidance = await self.generate_guidance(interest, state.teacher_profile)
        except Exception as exc:  # final safety net — the graph must never crash
            logger.exception("career guidance failed unexpectedly")
            guidance = _degraded_guidance(f"Career guidance failed: {exc}")

        state.agent_output = {"type": "career", **guidance.model_dump()}
        state.metadata["career_grounding"] = guidance.grounding
        state.messages.append(Message(role="assistant", content=_format_summary(guidance)))
        return state

    async def generate_guidance(
        self, interest: str, profile: TeacherProfile | None = None
    ) -> CareerGuidance:
        """Retrieve matching paths and produce honest, grounded guidance."""
        chunks = await self._retrieve(interest, profile)
        strong = [c for c in chunks if c.dense_score >= _DENSE_RELEVANCE][:_MAX_PATHS]
        grounding: CareerGrounding = "grounded" if strong else "general"

        messages = _build_messages(interest, profile, strong)
        parsed = await self._call_model(messages)
        if parsed is None:
            return _degraded_guidance("Career guidance could not be generated reliably.")

        return _assemble_guidance(parsed, strong, grounding)

    async def _retrieve(
        self, interest: str, profile: TeacherProfile | None
    ) -> list[RetrievedChunk]:
        subjects = " ".join(profile.subjects) if profile and profile.subjects else ""
        query = f"{interest} {subjects}".strip()
        try:
            return await self.retriever.retrieve(query, limit=6)
        except Exception as exc:  # embedder/store trouble must degrade, not crash
            logger.warning("career retrieval failed, giving general guidance: %s", exc)
            return []

    async def _call_model(self, messages: list[ChatMessage]) -> _LLMGuidance | None:
        for attempt in range(2):
            try:
                completion = await self.router.complete(
                    messages, task_type="bulk", json_mode=True, temperature=0.4, max_tokens=1536
                )
            except ProviderError as exc:
                logger.warning("career provider call failed: %s", exc)
                return None
            parsed = _parse_guidance(completion.text)
            if parsed is not None:
                return parsed
            if attempt == 0:
                messages = [
                    *messages,
                    ChatMessage(role="assistant", content=completion.text),
                    ChatMessage(
                        role="user",
                        content="Reply with ONLY the JSON object in the required schema.",
                    ),
                ]
        return None


# --- module-level helpers -------------------------------------------------------


def _last_user_text(state: CopilotState) -> str | None:
    for message in reversed(state.messages):
        if message.role == "user":
            return message.content if isinstance(message.content, str) else None
    return None


def _parse_guidance(text: str) -> _LLMGuidance | None:
    try:
        data = extract_json(text)
    except JSONExtractionError:
        return None
    try:
        return _LLMGuidance.model_validate(data)
    except ValidationError:
        return None


def _build_messages(
    interest: str, profile: TeacherProfile | None, chunks: list[RetrievedChunk]
) -> list[ChatMessage]:
    header_lines = [f"Teacher's interest / situation: {interest or 'general career growth'}"]
    if profile:
        if profile.subjects:
            header_lines.append(f"Subjects taught: {', '.join(profile.subjects)}")
        header_lines.append(f"Years of experience: {profile.years_experience}")
    header = "\n".join(header_lines)

    if chunks:
        paths = "\n\n".join(f"[{i + 1}]\n{c.text}" for i, c in enumerate(chunks))
        user = f"{header}\n\nCandidate career paths (recommend only from these):\n{paths}"
        system = _GROUNDED_SYSTEM
    else:
        user = header
        system = _GENERAL_SYSTEM
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def _assemble_guidance(
    parsed: _LLMGuidance, chunks: list[RetrievedChunk], grounding: CareerGrounding
) -> CareerGuidance:
    # Map lowercased dataset titles -> original, so citations reference real paths only.
    dataset_titles = {c.source.lower(): c.source for c in chunks if c.source}
    matched = [
        MatchedPath(
            title=path.title,
            why_it_fits=path.why_it_fits,
            skills_to_build=path.skills_to_build,
            first_steps=path.first_steps,
            source=dataset_titles.get(path.title.strip().lower()),
        )
        for path in parsed.matched_paths
        if path.title
    ]
    caveats = parsed.caveats or []
    # Realism guardrail: honest caveats must always be present.
    if not caveats:
        caveats = list(_DEFAULT_CAVEATS)
    return CareerGuidance(
        matched_paths=matched,
        honest_caveats=caveats,
        grounding=grounding,
        disclaimer=_GENERAL_DISCLAIMER if grounding == "general" else None,
    )


def _degraded_guidance(reason: str) -> CareerGuidance:
    return CareerGuidance(
        matched_paths=[],
        honest_caveats=list(_DEFAULT_CAVEATS),
        grounding="general",
        disclaimer=reason,
    )


def _format_summary(guidance: CareerGuidance) -> str:
    grounded = guidance.grounding == "grounded"
    badge = "✅ Grounded in curated paths" if grounded else "◐ General guidance"
    lines = [f"**Career directions** — {badge}"]
    if guidance.disclaimer:
        lines.append(f"_{guidance.disclaimer}_")
    for path in guidance.matched_paths:
        cite = f" _(based on: {path.source})_" if path.source else ""
        lines.append(f"\n**{path.title}**{cite} — {path.why_it_fits}")
        if path.skills_to_build:
            lines.append("  - Skills to build: " + ", ".join(path.skills_to_build))
        if path.first_steps:
            lines.append("  - First steps: " + "; ".join(path.first_steps))
    if guidance.honest_caveats:
        lines.append("\n**Honest caveats:**")
        lines.extend(f"- {c}" for c in guidance.honest_caveats)
    return "\n".join(lines)

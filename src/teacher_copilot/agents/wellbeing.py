"""Wellbeing agent (Phase 5).

================================  READ THIS FIRST  ============================
WHAT THIS DELIBERATELY IS NOT:
  - NOT therapy, NOT counselling, NOT diagnosis, NOT a mental-health assessment.
  - It never diagnoses, never uses clinical/DSM language, never scores or rates a
    person's mental state, and never implies it can treat anything.

WHAT IT IS:
  - A workload-AWARENESS and supportive-REFLECTION tool. It surfaces patterns from
    the teacher's own self-reported workload data (papers graded, classes taken,
    energy 1-5) and responds like a caring colleague with warmth and practical,
    NON-medical suggestions (rest, boundaries, talking to a colleague or admin).

SAFETY DESIGN:
  1. A high-recall crisis pre-filter runs FIRST on the message. If it detects any
     signal of serious distress or self-harm, the agent does NOT analyse or
     problem-solve — it responds briefly and warmly and hands off to real, region-
     appropriate professional resources (config-driven; see WELLBEING_RESOURCES).
     It never claims confidentiality, never promises outcomes, and always encourages
     reaching out to trusted people and professionals.
  2. The NUMBERS are computed in plain Python, not by the LLM — so pattern claims
     ("avg energy 2/5 over 5 days") are real, never hallucinated. The LLM only
     phrases warmth and suggestions around those computed facts.
  3. A disclaimer stating this isn't medical advice is ALWAYS present.

The tone is a caring colleague — not a therapist, not a cheerleader. No toxic
positivity. Teaching in India is genuinely demanding, and it says so.
==============================================================================
"""

from __future__ import annotations

import logging
import statistics
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.config import WellbeingResource, get_settings
from teacher_copilot.memory.profile import (
    ProfileStore,
    TeacherProfile,
    WorkloadEntry,
    get_profile_store,
)
from teacher_copilot.orchestrator.state import CopilotState, Message
from teacher_copilot.providers.errors import ProviderError
from teacher_copilot.providers.json_utils import JSONExtractionError, extract_json
from teacher_copilot.providers.router import ChatMessage, ProviderRouter, get_router

logger = logging.getLogger("teacher_copilot.agents.wellbeing")

# Resource alias so callers see a wellbeing-domain name.
Resource = WellbeingResource

ToneFlag = Literal["routine", "elevated_workload", "distress_handoff"]

_RECENT_WINDOW = 7  # how many recent logged days to reflect on
_LOW_ENERGY_AVG = 2.5  # avg energy at/below this over the window reads as elevated strain
_HIGH_LOAD_CLASSES = 5  # a "high-load" teaching day
_CONSECUTIVE_HIGH_LOAD = 3  # this many back-to-back high-load days reads as elevated

_DISCLAIMER = (
    "I'm a workload-reflection tool, not a medical or mental-health professional — "
    "this isn't a diagnosis or treatment. If things feel heavy, please consider "
    "reaching out to someone you trust or a professional."
)

# High-recall crisis screen. Intentionally errs toward over-triggering the gentle
# handoff: missing a genuine signal is far worse than a false positive. These are
# serious-distress / self-harm phrases, kept specific enough to avoid trivial matches
# (e.g. "give up on life", not a bare "give up").
_CRISIS_SIGNALS: tuple[str, ...] = (
    "kill myself",
    "killing myself",
    "want to die",
    "wanna die",
    "end my life",
    "ending my life",
    "end it all",
    "take my own life",
    "no reason to live",
    "nothing to live for",
    "no point in living",
    "better off dead",
    "better off without me",
    "suicidal",
    "suicide",
    "self-harm",
    "self harm",
    "harm myself",
    "hurt myself",
    "cut myself",
    "don't want to be here",
    "dont want to be here",
    "can't go on",
    "cant go on",
    "give up on life",
)

_CRISIS_MESSAGE = (
    "I'm really glad you told me, and I'm sorry things feel this heavy right now. "
    "This is more than I'm able to help with, and you deserve real support — please "
    "don't carry it alone. Reaching out to someone you trust, or one of the "
    "professionals below, can genuinely help. You matter."
)

_WELLBEING_SYSTEM_PROMPT = (
    "You are a caring, down-to-earth colleague to a school teacher in India. You are "
    "NOT a therapist or medical professional. Do NOT diagnose, do NOT use clinical or "
    "mental-health-assessment language, do NOT rate their mental state. The workload "
    "observations you are given were computed from the teacher's own logs and are "
    "TRUE — reflect them back warmly, but never invent numbers or statistics. Offer "
    "practical, NON-medical suggestions only (rest, small boundaries, leaning on a "
    "colleague or admin, protecting time). Acknowledge honestly that teaching here is "
    "demanding. No toxic positivity.\n\n"
    'Output ONLY this JSON, no prose:\n'
    '{"patterns": ["short, human observations"], "supportive_message": "2-4 warm '
    'sentences", "practical_suggestions": ["non-medical, doable"]}'
)


class WorkloadSignals(BaseModel):
    """Transparent, Python-computed signals over the recent workload window."""

    days: int = 0
    avg_energy: float = 0.0
    total_papers: int = 0
    total_classes: int = 0
    consecutive_high_load: int = 0
    low_energy_days: int = 0


class WellbeingReflection(BaseModel):
    """A supportive, non-clinical reflection. ``disclaimer`` is always present."""

    observations: list[str] = Field(default_factory=list, description="Python-computed facts.")
    patterns: list[str] = Field(default_factory=list)
    supportive_message: str = ""
    practical_suggestions: list[str] = Field(default_factory=list)
    resources: list[Resource] = Field(
        default_factory=list, description="Populated only on the distress handoff."
    )
    disclaimer: str = _DISCLAIMER
    tone_flag: ToneFlag = "routine"


class _LLMReflection(BaseModel):
    """Lenient shape of the LLM's phrasing output (facts stay Python-computed)."""

    patterns: list[str] = Field(default_factory=list)
    supportive_message: str = ""
    practical_suggestions: list[str] = Field(default_factory=list)


def contains_distress_signal(text: str) -> bool:
    """High-recall screen for serious-distress / self-harm phrases in ``text``."""
    lowered = text.lower()
    return any(signal in lowered for signal in _CRISIS_SIGNALS)


def compute_signals(entries: list[WorkloadEntry]) -> WorkloadSignals:
    """Compute transparent workload signals over the most recent window (pure Python)."""
    recent = entries[-_RECENT_WINDOW:]
    if not recent:
        return WorkloadSignals()

    consecutive = 0
    for entry in reversed(recent):
        if entry.classes_taken >= _HIGH_LOAD_CLASSES:
            consecutive += 1
        else:
            break

    return WorkloadSignals(
        days=len(recent),
        avg_energy=round(statistics.mean(e.self_reported_energy for e in recent), 2),
        total_papers=sum(e.papers_graded for e in recent),
        total_classes=sum(e.classes_taken for e in recent),
        consecutive_high_load=consecutive,
        low_energy_days=sum(1 for e in recent if e.self_reported_energy <= 2),
    )


def _observations_from(signals: WorkloadSignals) -> list[str]:
    if signals.days == 0:
        return []
    observations = [
        f"Over your last {signals.days} logged days: average energy "
        f"{signals.avg_energy}/5, {signals.total_papers} papers graded, "
        f"{signals.total_classes} classes taught."
    ]
    if signals.consecutive_high_load >= _CONSECUTIVE_HIGH_LOAD:
        observations.append(
            f"{signals.consecutive_high_load} days in a row with "
            f"{_HIGH_LOAD_CLASSES}+ classes."
        )
    if signals.low_energy_days:
        observations.append(
            f"{signals.low_energy_days} of the last {signals.days} days logged energy "
            "at 2/5 or lower."
        )
    return observations


def _tone_for(signals: WorkloadSignals) -> ToneFlag:
    if signals.days == 0:
        return "routine"
    low_energy = signals.avg_energy <= _LOW_ENERGY_AVG
    sustained_load = signals.consecutive_high_load >= _CONSECUTIVE_HIGH_LOAD
    if low_energy or sustained_load:
        return "elevated_workload"
    return "routine"


class WellbeingAgent(BaseAgent):
    """Non-clinical workload check-in and pattern-surfacing agent."""

    name = "wellbeing"
    description = "Logs workload signals and surfaces patterns (non-clinical, non-diagnostic)."

    def __init__(
        self, *, router: ProviderRouter | None = None, profile_store: ProfileStore | None = None
    ) -> None:
        self._router = router
        self._profile_store = profile_store

    @property
    def router(self) -> ProviderRouter:
        return self._router if self._router is not None else get_router()

    @property
    def profile_store(self) -> ProfileStore:
        return self._profile_store if self._profile_store is not None else get_profile_store()

    async def run(self, state: CopilotState) -> CopilotState:
        """Reflect on workload (or hand off on distress). Never analyses on crisis."""
        state.active_agent = self.name
        message = _last_user_text(state) or ""

        # SAFETY: crisis screen runs first. No analysis, no problem-solving on trigger.
        if contains_distress_signal(message):
            logger.info("wellbeing: distress signal detected — gentle handoff, no analysis")
            reflection = self._distress_handoff()
            state.agent_output = {"type": "wellbeing", **reflection.model_dump()}
            state.metadata["wellbeing_tone"] = reflection.tone_flag
            state.messages.append(Message(role="assistant", content=_format_summary(reflection)))
            return state

        profile = state.teacher_profile
        entries = profile.workload_log if profile else []
        signals = compute_signals(entries)
        observations = _observations_from(signals)
        tone = _tone_for(signals)

        reflection = await self._reflect(message, observations, signals, tone)
        state.agent_output = {"type": "wellbeing", **reflection.model_dump()}
        state.metadata["wellbeing_tone"] = reflection.tone_flag
        state.metadata["wellbeing_signals"] = signals.model_dump()
        state.messages.append(Message(role="assistant", content=_format_summary(reflection)))
        return state

    def _distress_handoff(self) -> WellbeingReflection:
        return WellbeingReflection(
            observations=[],
            patterns=[],
            supportive_message=_CRISIS_MESSAGE,
            practical_suggestions=[],
            resources=list(get_settings().wellbeing_resources),
            tone_flag="distress_handoff",
        )

    async def _reflect(
        self,
        message: str,
        observations: list[str],
        signals: WorkloadSignals,
        tone: ToneFlag,
    ) -> WellbeingReflection:
        """LLM phrasing around the Python-computed facts, with a safe fallback."""
        facts = "\n".join(observations) if observations else "No workload has been logged yet."
        user = (
            f"The teacher said: {message!r}\n\n"
            f"Computed workload observations (these are TRUE, do not change the numbers):\n"
            f"{facts}"
        )
        messages = [
            ChatMessage(role="system", content=_WELLBEING_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user),
        ]
        parsed = await self._call_model(messages)
        if parsed is None:
            return _fallback_reflection(observations, tone)
        return WellbeingReflection(
            observations=observations,
            patterns=parsed.patterns,
            supportive_message=parsed.supportive_message or _DEFAULT_SUPPORT,
            practical_suggestions=parsed.practical_suggestions,
            resources=[],
            tone_flag=tone,
        )

    async def _call_model(self, messages: list[ChatMessage]) -> _LLMReflection | None:
        for attempt in range(2):
            try:
                completion = await self.router.complete(
                    messages, task_type="fast", json_mode=True, temperature=0.5, max_tokens=512
                )
            except ProviderError as exc:
                logger.warning("wellbeing provider call failed: %s", exc)
                return None
            parsed = _parse_reflection(completion.text)
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

    async def log_workload(self, teacher_id: str, entry: WorkloadEntry) -> TeacherProfile:
        """Convenience: append a day's workload for a teacher (used by the demo)."""
        return await self.profile_store.append_workload(teacher_id, entry)


# --- module-level helpers -------------------------------------------------------

_DEFAULT_SUPPORT = (
    "Teaching in India asks a lot of you, and it's okay for some weeks to feel heavier "
    "than others. Be as kind to yourself as you are to your students."
)


def _last_user_text(state: CopilotState) -> str | None:
    for message in reversed(state.messages):
        if message.role == "user":
            return message.content if isinstance(message.content, str) else None
    return None


def _parse_reflection(text: str) -> _LLMReflection | None:
    try:
        data = extract_json(text)
    except JSONExtractionError:
        return None
    try:
        return _LLMReflection.model_validate(data)
    except ValidationError:
        return None


def _fallback_reflection(observations: list[str], tone: ToneFlag) -> WellbeingReflection:
    suggestions = [
        "If you can, protect a small block of time today that's just for you.",
        "It often helps to name the load out loud to a colleague or your admin.",
    ]
    return WellbeingReflection(
        observations=observations,
        patterns=[],
        supportive_message=_DEFAULT_SUPPORT,
        practical_suggestions=suggestions,
        resources=[],
        tone_flag=tone,
    )


def _format_summary(reflection: WellbeingReflection) -> str:
    lines: list[str] = []
    if reflection.tone_flag == "distress_handoff":
        lines.append(reflection.supportive_message)
        if reflection.resources:
            lines.append("\n**People who can help:**")
            for resource in reflection.resources:
                lines.append(f"- {resource.name}: {resource.contact} — {resource.description}")
        lines.append(f"\n_{reflection.disclaimer}_")
        return "\n".join(lines)

    if reflection.observations:
        lines.append("**What your logs show:** " + " ".join(reflection.observations))
    if reflection.supportive_message:
        lines.append("\n" + reflection.supportive_message)
    if reflection.practical_suggestions:
        lines.append("\n**A few small things that might help:**")
        lines.extend(f"- {s}" for s in reflection.practical_suggestions)
    lines.append(f"\n_{reflection.disclaimer}_")
    return "\n".join(lines)

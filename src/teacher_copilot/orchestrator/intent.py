"""Intent classification node (Phase 2).

Reads the latest user message and sets ``state.intent`` so the graph can route to
the right specialist. The primary path asks the ``fast`` model tier for a strict
JSON verdict; if that fails to parse or returns garbage, we retry once with a
corrective nudge and then fall back to a keyword heuristic. The graph must never
crash on a malformed LLM response — a misroute is recoverable, a crash is not.
"""

from __future__ import annotations

import logging

from teacher_copilot.orchestrator.state import CopilotState, Intent
from teacher_copilot.providers.errors import ProviderError
from teacher_copilot.providers.json_utils import JSONExtractionError, extract_json
from teacher_copilot.providers.router import ChatMessage, ProviderRouter, get_router

logger = logging.getLogger("teacher_copilot.orchestrator")

# Below this confidence we prefer the safe general path over a risky specialist
# route (e.g. don't send a wellbeing vent to the grading agent).
_MIN_CONFIDENCE = 0.5
_HEURISTIC_CONFIDENCE = 0.3

_SYSTEM_PROMPT = """\
You are the router for a copilot used by school teachers in India. Classify the \
teacher's LAST message into exactly ONE intent:

- grading: checking/marking/evaluating student answers, papers, marks, rubrics.
- lesson_plan: planning lessons, chapters, syllabus, classroom activities.
- wellbeing: fatigue, stress, workload, exhaustion, how the teacher is coping.
- career: upskilling, switching roles, edtech/L&D/instructional-design paths.
- general: greetings, small talk, or anything that fits none of the above.

Examples:
- "check these class 9 science answers against the rubric" -> grading
- "how many marks should this history answer get?" -> grading
- "plan chapter 4 of class 8 maths for next week" -> lesson_plan
- "I need a fun activity to teach photosynthesis" -> lesson_plan
- "I'm exhausted after three days of invigilation duty" -> wellbeing
- "the workload this term is crushing me" -> wellbeing
- "should I move into edtech content roles?" -> career
- "what upskilling helps me pivot to instructional design?" -> career
- "hello, what can you help me with?" -> general

Respond with ONLY a JSON object, no prose:
{"intent": "<one of: grading|lesson_plan|wellbeing|career|general>", \
"confidence": <float 0.0-1.0>}"""

# Documented fallback: substring hints per intent, scanned when the LLM path fails.
# Order matters only for readability; scoring picks the best-matching intent.
_KEYWORD_MAP: dict[Intent, tuple[str, ...]] = {
    Intent.GRADING: (
        "grade", "grading", "marks", "mark this", "check these", "answer sheet",
        "answers", "evaluate", "correct", "rubric", "paper", "score",
    ),
    Intent.LESSON_PLAN: (
        "lesson plan", "lesson", "plan chapter", "chapter", "syllabus", "teach",
        "activity", "prepare a class", "curriculum for", "worksheet",
    ),
    Intent.WELLBEING: (
        "exhausted", "tired", "stressed", "stress", "burnout", "burnt out",
        "overwhelmed", "invigilation", "workload", "drained", "cope", "energy",
    ),
    Intent.CAREER: (
        "career", "switch", "pivot", "edtech", "upskill", "instructional design",
        "curriculum consulting", "l&d", "job", "new role", "transition into",
    ),
}


def _last_user_message(state: CopilotState) -> str | None:
    """Return the text of the most recent user message, if any."""
    for message in reversed(state.messages):
        if message.role == "user":
            return message.content if isinstance(message.content, str) else None
    return None


def _parse_verdict(text: str) -> tuple[Intent, float] | None:
    """Parse a ``{"intent": ..., "confidence": ...}`` object; None if unusable."""
    try:
        data = extract_json(text)
    except JSONExtractionError:
        return None
    if "intent" not in data:
        return None
    raw_intent = str(data["intent"]).strip().lower()
    if raw_intent not in set(Intent):
        return None
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return Intent(raw_intent), max(0.0, min(1.0, confidence))


def _keyword_heuristic(message: str) -> Intent:
    """Score the message against the keyword map; return the best intent (or general)."""
    lowered = message.lower()
    best_intent = Intent.GENERAL
    best_score = 0
    for intent, keywords in _KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in lowered)
        if score > best_score:
            best_intent, best_score = intent, score
    return best_intent


async def _classify_via_llm(router: ProviderRouter, message: str) -> tuple[Intent, float] | None:
    """LLM path with one corrective retry. None if both attempts are unusable."""
    messages = [
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(role="user", content=message),
    ]
    for attempt in range(2):
        try:
            result = await router.complete(
                messages, task_type="fast", json_mode=True, temperature=0.0, max_tokens=64
            )
        except ProviderError as exc:
            logger.warning("intent LLM call failed (attempt %d): %s", attempt + 1, exc)
            return None
        verdict = _parse_verdict(result.text)
        if verdict is not None:
            return verdict
        # Corrective nudge before giving up.
        messages.append(ChatMessage(role="assistant", content=result.text))
        messages.append(
            ChatMessage(
                role="user",
                content='That was not valid. Reply with ONLY {"intent": "...", '
                '"confidence": 0.0-1.0} and nothing else.',
            )
        )
    return None


async def classify_intent(
    state: CopilotState, *, router: ProviderRouter | None = None
) -> CopilotState:
    """Classify the latest user message and set ``state.intent`` (never raises).

    Args:
        state: Current orchestrator state (expects at least one user message).
        router: Provider router to use; defaults to the process-wide router.

    Returns:
        The same state with ``intent`` set and ``metadata['intent_confidence']`` recorded.
    """
    router = router or get_router()
    message = _last_user_message(state)
    if not message:
        state.intent = Intent.GENERAL
        state.metadata["intent_confidence"] = 0.0
        return state

    verdict = await _classify_via_llm(router, message)
    if verdict is None:
        # LLM path failed entirely: the keyword heuristic's decision is authoritative.
        # We record a low confidence (0.3) as an honesty signal, but we do NOT run it
        # through the <0.5 gate below — otherwise the keyword map could never route.
        intent, confidence, source = _keyword_heuristic(message), _HEURISTIC_CONFIDENCE, "heuristic"
    else:
        # The LLM answered. If it is unsure, prefer the safe general path over a
        # possible misroute (e.g. a wellbeing vent sent to grading).
        intent, confidence, source = *verdict, "llm"
        if confidence < _MIN_CONFIDENCE:
            intent = Intent.GENERAL

    state.intent = intent
    state.metadata["intent_confidence"] = confidence
    state.metadata["intent_source"] = source
    logger.info("intent=%s confidence=%.2f source=%s", intent, confidence, source)
    return state

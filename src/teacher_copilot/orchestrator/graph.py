"""LangGraph assembly (Phase 2).

Wires the orchestrator graph:

    START -> load_profile -> classify_intent -> (route by intent) -> agent -> END

``CopilotState`` (a Pydantic model) is used directly as the graph schema; nodes
receive a state instance and return a **partial dict of field updates**, which
LangGraph merges. We keep ``CopilotState`` as the domain object and never let graph
concerns leak into it — the only adaptation is that ``ainvoke`` returns a plain dict,
which :func:`run_turn` revalidates back into a ``CopilotState``.

Grading is live (Phase 3). The other specialists (lesson_plan/wellbeing/career) are
still Phase 0 stubs that raise ``NotImplementedError``; their nodes catch that and
emit a graceful ``not_implemented`` output, so the graph always runs end-to-end.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from teacher_copilot.agents.base import BaseAgent
from teacher_copilot.agents.career import CareerAgent
from teacher_copilot.agents.grading import GradingAgent
from teacher_copilot.agents.lesson_plan import LessonPlanAgent
from teacher_copilot.agents.wellbeing import WellbeingAgent
from teacher_copilot.memory.profile import ProfileStore, get_profile_store
from teacher_copilot.orchestrator.intent import classify_intent
from teacher_copilot.orchestrator.state import CopilotState, Intent, Message
from teacher_copilot.providers.errors import ProviderError
from teacher_copilot.providers.router import ChatMessage, ProviderRouter, get_router

logger = logging.getLogger("teacher_copilot.orchestrator")

NodeFn = Callable[[CopilotState], Awaitable[dict[str, Any]]]

# Which future phase delivers each specialist (for the friendly stub message).
_AGENT_PHASE = {"grading": 3, "lesson_plan": 4, "wellbeing": 5, "career": 5}

# Intent -> graph node. GENERAL is handled inline by the orchestrator.
_INTENT_TO_NODE: dict[Intent, str] = {
    Intent.GRADING: "grading",
    Intent.LESSON_PLAN: "lesson_plan",
    Intent.WELLBEING: "wellbeing",
    Intent.CAREER: "career",
    Intent.GENERAL: "general_response",
}

_GENERAL_SYSTEM_PROMPT = (
    "You are Teacher Copilot, a concise, warm assistant for school teachers in "
    "India. Be practical and encouraging. Keep replies short unless asked for more. "
    "If a request clearly needs grading, lesson planning, wellbeing check-ins, or "
    "career guidance, help directly and briefly."
)


def _make_load_profile_node(store: ProfileStore) -> NodeFn:
    async def load_profile(state: CopilotState) -> dict[str, Any]:
        teacher_id = state.metadata.get("teacher_id")
        if not teacher_id:
            return {}
        profile = await store.load(str(teacher_id))
        return {"teacher_profile": profile}

    return load_profile


def _make_classify_node(router: ProviderRouter) -> NodeFn:
    async def classify(state: CopilotState) -> dict[str, Any]:
        updated = await classify_intent(state, router=router)
        return {"intent": updated.intent, "metadata": updated.metadata}

    return classify


def _make_agent_node(agent: BaseAgent) -> NodeFn:
    async def run_agent(state: CopilotState) -> dict[str, Any]:
        try:
            updated = await agent.run(state)
            return {
                "active_agent": updated.active_agent or agent.name,
                "agent_output": updated.agent_output,
                "messages": updated.messages,
            }
        except NotImplementedError:
            phase = _AGENT_PHASE.get(agent.name, 0)
            reply = (
                f"The {agent.name.replace('_', ' ')} assistant isn't available yet — "
                f"it's coming in Phase {phase}. For now I can still chat generally."
            )
            logger.info("agent '%s' not implemented; returning graceful stub", agent.name)
            return {
                "active_agent": agent.name,
                "agent_output": {
                    "type": "not_implemented",
                    "agent": agent.name,
                    "phase": phase,
                    "message": reply,
                },
                "messages": [*state.messages, Message(role="assistant", content=reply)],
            }

    return run_agent


def _make_general_node(router: ProviderRouter) -> NodeFn:
    async def general_response(state: CopilotState) -> dict[str, Any]:
        chat: list[ChatMessage] = [ChatMessage(role="system", content=_GENERAL_SYSTEM_PROMPT)]
        for message in state.messages:
            if isinstance(message.content, str):
                chat.append(ChatMessage(role=message.role, content=message.content))
        try:
            result = await router.complete(chat, task_type="fast", max_tokens=512)
            reply = result.text.strip() or "Sorry, I didn't catch that — could you rephrase?"
            output: dict[str, Any] = {"type": "general", "text": reply, "provider": result.provider}
        except ProviderError as exc:
            logger.warning("general path providers exhausted: %s", exc)
            reply = "The system is busy right now — please try again in a moment."
            output = {"type": "error", "text": reply}
        return {
            "active_agent": "general",
            "agent_output": output,
            "messages": [*state.messages, Message(role="assistant", content=reply)],
        }

    return general_response


def _route_by_intent(state: CopilotState) -> str:
    return _INTENT_TO_NODE[state.intent]


def build_graph(
    *, router: ProviderRouter | None = None, profile_store: ProfileStore | None = None
) -> Any:
    """Build and compile the orchestrator LangGraph.

    Args:
        router: Provider router for LLM calls (defaults to the process-wide router).
        profile_store: Teacher profile store (defaults to the process-wide store).

    Returns:
        A compiled LangGraph runnable over :class:`CopilotState`.
    """
    router = router or get_router()
    profile_store = profile_store or get_profile_store()

    # Grading is live (Phase 3) and shares the graph's router. The others are still
    # stubs whose nodes emit a graceful "coming soon" reply (see _make_agent_node).
    agents: list[BaseAgent] = [
        GradingAgent(router=router),
        LessonPlanAgent(),
        WellbeingAgent(),
        CareerAgent(),
    ]

    graph: StateGraph = StateGraph(CopilotState)
    graph.add_node("load_profile", _make_load_profile_node(profile_store))
    graph.add_node("classify_intent", _make_classify_node(router))
    for agent in agents:
        graph.add_node(agent.name, _make_agent_node(agent))
    graph.add_node("general_response", _make_general_node(router))

    graph.add_edge(START, "load_profile")
    graph.add_edge("load_profile", "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _route_by_intent,
        {node: node for node in _INTENT_TO_NODE.values()},
    )
    for node in _INTENT_TO_NODE.values():
        graph.add_edge(node, END)

    return graph.compile()


async def run_turn(
    graph: Any,
    teacher_id: str,
    message: str,
    state: CopilotState | None = None,
) -> CopilotState:
    """Run one conversational turn — the single entry point the API will call.

    Appends ``message`` as a user turn, invokes the graph, and returns the updated
    :class:`CopilotState` (revalidated from LangGraph's dict result).
    """
    state = state or CopilotState()
    state.messages.append(Message(role="user", content=message))
    state.metadata["teacher_id"] = teacher_id
    result: dict[str, Any] = await graph.ainvoke(state)
    return CopilotState.model_validate(result)

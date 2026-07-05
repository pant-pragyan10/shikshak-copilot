#!/usr/bin/env python
"""Talk to the orchestrator from the terminal.

Creates a demo teacher profile, then runs each line you type through the full graph
(load profile -> classify intent -> route) and prints the detected intent plus the
reply. Needs real provider keys in ``.env`` for the LLM path; without them the
classifier falls back to its keyword heuristic and the general path will report the
system as busy.

    python scripts/chat_demo.py

Type 'exit' or Ctrl-D to quit.
"""

from __future__ import annotations

import asyncio

from teacher_copilot.memory.profile import Board, TeacherProfile, get_profile_store
from teacher_copilot.orchestrator.graph import build_graph, run_turn
from teacher_copilot.orchestrator.state import CopilotState

DEMO_TEACHER_ID = "demo-teacher"


async def _ensure_demo_profile() -> None:
    store = get_profile_store()
    if await store.load(DEMO_TEACHER_ID) is None:
        await store.save(
            TeacherProfile(
                teacher_id=DEMO_TEACHER_ID,
                name="Ananya",
                subjects=["Science", "Maths"],
                grades_taught=["8", "9"],
                board=Board.CBSE,
                years_experience=6,
            )
        )


async def main() -> None:
    await _ensure_demo_profile()
    graph = build_graph()
    state: CopilotState | None = None

    print("Teacher Copilot — orchestrator demo. Type 'exit' to quit.\n")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in {"exit", "quit"}:
            break

        state = await run_turn(graph, DEMO_TEACHER_ID, line, state)
        confidence = state.metadata.get("intent_confidence")
        reply = state.messages[-1].content if state.messages else ""
        print(f"[intent={state.intent} confidence={confidence}]")
        print(f"copilot> {reply}\n")


if __name__ == "__main__":
    asyncio.run(main())

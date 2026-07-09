"""API tests — httpx ASGITransport, all LLM + embedder mocked (no network, no 2GB model)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from teacher_copilot.api.errors import register_exception_handlers
from teacher_copilot.api.main import create_app
from teacher_copilot.memory.profile import ProfileStore
from teacher_copilot.providers.errors import ProviderExhaustedError
from teacher_copilot.providers.types import CompletionResult, Provider

# --- fakes ----------------------------------------------------------------------

_INTENT = '{{"intent": "{intent}", "confidence": 0.95}}'
_RUBRIC = '{"criteria": [{"name": "Accuracy", "description": "x", "max_marks": 3}]}'
_GRADE = json.dumps(
    {
        "scores": [{"criterion_name": "Accuracy", "awarded_marks": 3, "justification": "correct"}],
        "strengths": ["clear"],
        "improvements": ["add detail"],
        "overall_comment": "Good.",
        "status": "graded",
        "confidence": 0.8,
    }
)
_PLAN = json.dumps(
    {
        "objectives": ["explain reflection"],
        "materials": ["mirror"],
        "timeline": [
            {"title": "Intro", "minutes": 10, "activities": ["recall"], "teacher_notes": ""}
        ],
        "assessment_ideas": ["exit ticket"],
        "homework": ["3 qs"],
        "differentiation": ["scaffold", "extend"],
    }
)
_CAREER = json.dumps(
    {
        "matched_paths": [
            {
                "title": "Instructional Designer",
                "why_it_fits": "fits",
                "skills_to_build": ["ADDIE"],
                "first_steps": ["course"],
            }
        ],
        "caveats": ["takes time"],
    }
)
_WELLBEING = json.dumps(
    {
        "patterns": ["busy week"],
        "supportive_message": "You did a lot.",
        "practical_suggestions": ["rest"],
    }
)


class FakeRouter:
    """Serves the right canned JSON per agent by sniffing the system prompt."""

    def __init__(self, *, intent: str = "grading", raise_exhausted: bool = False) -> None:
        self.intent = intent
        self.raise_exhausted = raise_exhausted
        self.calls = 0

    async def complete(
        self,
        messages: list[Any],
        *,
        task_type: str = "fast",
        json_mode: bool = False,
        **kwargs: Any,
    ) -> CompletionResult:
        self.calls += 1
        if self.raise_exhausted:
            raise ProviderExhaustedError("all providers down", failures={})
        system = ""
        for m in messages:
            if m.role == "system" and isinstance(m.content, str):
                system = m.content.lower()
                break
        if not json_mode:
            text = "Here to help!"
        elif "classify" in system:
            text = _INTENT.format(intent=self.intent)
        elif "marking rubric" in system:
            text = _RUBRIC
        elif "grading a school" in system:
            text = _GRADE
        elif "lesson" in system:
            text = _PLAN
        elif "career mentor" in system:
            text = _CAREER
        elif "colleague" in system:
            text = _WELLBEING
        else:
            text = "{}"
        return CompletionResult(text=text, provider=Provider.GROQ, model="m")

    async def health(self) -> dict[str, dict[str, bool]]:
        return {"groq": {"configured": True, "disabled": False}}


class _EmptyRetriever:
    async def retrieve(self, query: str, **kwargs: Any) -> list[Any]:
        return []


def _build_app(
    tmp_path: Path, *, intent: str = "grading", raise_exhausted: bool = False
) -> FastAPI:
    return create_app(
        router=FakeRouter(intent=intent, raise_exhausted=raise_exhausted),  # type: ignore[arg-type]
        profile_store=ProfileStore(base_path=str(tmp_path)),
        retriever=_EmptyRetriever(),  # type: ignore[arg-type]
        career_retriever=_EmptyRetriever(),  # type: ignore[arg-type]
    )


def _client(app: FastAPI) -> AsyncClient:
    # raise_app_exceptions=False so unhandled errors surface as 500 responses (exercising
    # our exception handlers) instead of propagating into the test.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        if event:
            events.append((event, json.loads(data) if data else {}))
    return events


# --- health ---------------------------------------------------------------------


async def test_health_reports_provider_health(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["providers"]["groq"]["configured"] is True


# --- chat -----------------------------------------------------------------------


async def test_chat_non_streaming_routes_grading(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path, intent="grading")) as client:
        resp = await client.post(
            "/chat",
            json={"teacher_id": "t1", "message": "Question: 2+2? Answer: 4. Please grade."},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "grading"
    assert body["agent_output"] is not None
    assert body["agent_output"]["type"] == "grading"
    assert body["session_id"]


async def test_chat_stream_emits_event_sequence(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path, intent="grading")) as client:
        resp = await client.post(
            "/chat/stream",
            json={"teacher_id": "t1", "message": "Question: 2+2? Answer: 4. grade please"},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    names = [e[0] for e in events]

    assert names[0] == "intent"
    assert "message" in names
    assert names[-1] == "done"
    assert names.index("intent") < names.index("message") < names.index("done")
    assert "agent_output" in names  # structured agent payload present
    intent_data = dict(events)["intent"]
    assert intent_data["intent"] == "grading"


# --- grading --------------------------------------------------------------------


async def test_grade_returns_graded_result(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.post(
            "/grade",
            json={
                "question": "What is 2+2?",
                "answer_text": "4",
                "rubric": {"criteria": [{"name": "Accuracy", "description": "x", "max_marks": 3}]},
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "graded"
    assert body["total_awarded"] == 3
    assert body["total_max"] == 3


async def test_grade_batch_handles_multiple(tmp_path: Path) -> None:
    rubric = {"criteria": [{"name": "Accuracy", "description": "x", "max_marks": 3}]}
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.post(
            "/grade/batch",
            json={
                "items": [
                    {"question": "q1", "answer_text": "a1", "rubric": rubric},
                    {"question": "q2", "answer_text": "a2", "rubric": rubric},
                ],
                "max_concurrency": 2,
            },
        )
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 2


async def test_grade_image_rejects_non_image(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.post(
            "/grade/image",
            files={"file": ("answer.txt", b"not an image", "text/plain")},
            data={"question": "grade this"},
        )
    assert resp.status_code == 415
    assert resp.json()["error"]["type"] == "http_error"


async def test_grade_image_rejects_oversized(tmp_path: Path) -> None:
    big = b"\x89PNG" + b"0" * (10 * 1024 * 1024 + 10)
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.post(
            "/grade/image",
            files={"file": ("answer.png", big, "image/png")},
            data={"question": "grade this"},
        )
    assert resp.status_code == 413


async def test_grade_image_accepts_image(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.post(
            "/grade/image",
            files={"file": ("answer.png", b"\x89PNGfakebytes", "image/png")},
            data={
                "question": "Label the diagram",
                "rubric_json": json.dumps(
                    {"criteria": [{"name": "Accuracy", "description": "x", "max_marks": 3}]}
                ),
            },
        )
    assert resp.status_code == 200
    assert resp.json()["total_max"] == 3


# --- profile --------------------------------------------------------------------


async def test_profile_roundtrip(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        missing = await client.get("/profile/t1")
        assert missing.status_code == 404

        put = await client.put(
            "/profile/t1",
            json={"name": "Meera", "subjects": ["Science"], "board": "CBSE", "years_experience": 5},
        )
        assert put.status_code == 200
        assert put.json()["teacher_id"] == "t1"

        got = await client.get("/profile/t1")
        assert got.status_code == 200
        assert got.json()["name"] == "Meera"

        wl = await client.post(
            "/profile/t1/workload",
            json={"entry_date": "2026-07-06", "papers_graded": 20, "classes_taken": 5,
                  "self_reported_energy": 2},
        )
        assert wl.status_code == 200
        assert len(wl.json()["workload_log"]) == 1


async def test_workload_on_missing_profile_404(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.post(
            "/profile/ghost/workload",
            json={"entry_date": "2026-07-06", "self_reported_energy": 3},
        )
    assert resp.status_code == 404


# --- tools ----------------------------------------------------------------------


async def test_lesson_plan_endpoint(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.post(
            "/lesson-plan",
            json={"topic": "reflection of light", "subject": "Science", "grade": "8",
                  "duration_minutes": 40},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["grounding"] == "general_knowledge"  # empty retriever -> general
    assert body["objectives"]


async def test_career_endpoint(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.post("/career", json={"interest": "move into edtech"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["grounding"] == "general"  # empty retriever
    assert body["honest_caveats"]  # always present


# --- CORS + error contract ------------------------------------------------------


async def test_cors_header_present_for_configured_origin(tmp_path: Path) -> None:
    async with _client(_build_app(tmp_path)) as client:
        resp = await client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_provider_exhausted_maps_to_503() -> None:
    # Handlers are tested directly: agents are defensive and rarely propagate, so we
    # assert the error->HTTP contract on a minimal app.
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ProviderExhaustedError("down", failures={})

    async with _client(app) as client:
        resp = await client.get("/boom")
    assert resp.status_code == 503
    assert resp.json()["error"]["type"] == "provider_exhausted"
    assert "busy" in resp.json()["error"]["message"].lower()


async def test_unhandled_error_does_not_leak_internals() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/kaboom")
    async def kaboom() -> None:
        raise RuntimeError("secret_api_key=sk-leaked-12345")

    async with _client(app) as client:
        resp = await client.get("/kaboom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["type"] == "internal_error"
    assert "secret_api_key" not in json.dumps(body)  # never leaks internals

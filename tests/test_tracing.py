"""Tracing tests — no real Langfuse. No-op behaviour + span assertions via a mock tracer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from teacher_copilot.config import Settings
from teacher_copilot.memory.profile import ProfileStore
from teacher_copilot.observability.tracing import NoOpTracer, get_tracer
from teacher_copilot.orchestrator.graph import build_graph, run_turn
from teacher_copilot.providers.router import ProviderRouter
from teacher_copilot.providers.types import ChatMessage, CompletionResult, Provider


class MockSpan:
    def __init__(self, name: str, kind: str, metadata: dict[str, Any] | None) -> None:
        self.name = name
        self.kind = kind
        self.metadata = metadata
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)

    def __enter__(self) -> MockSpan:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class MockTracer:
    def __init__(self) -> None:
        self.spans: list[MockSpan] = []

    def span(
        self, name: str, *, kind: str = "span", metadata: dict[str, Any] | None = None
    ) -> MockSpan:
        s = MockSpan(name, kind, metadata)
        self.spans.append(s)
        return s

    def flush(self) -> None:
        return None


class FakeClient:
    provider = Provider.GROQ
    default_model = "fake-model"

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        return CompletionResult(
            text="ok", provider=self.provider, model=model or self.default_model,
            input_tokens=11, output_tokens=7, latency_ms=12.3,
        )

    async def reachable(self) -> bool:
        return True


class FakeRouter:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self, messages: list[Any], *, json_mode: bool = False, **kwargs: Any
    ) -> CompletionResult:
        self.calls += 1
        text = '{"intent": "general", "confidence": 0.95}' if json_mode else "Hello there!"
        return CompletionResult(text=text, provider=Provider.GROQ, model="m")


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


# --- no-op behaviour -------------------------------------------------------------


def test_get_tracer_is_noop_when_unconfigured() -> None:
    get_tracer.cache_clear()
    tracer = get_tracer()  # real settings: no Langfuse keys -> no-op
    assert isinstance(tracer, NoOpTracer)


def test_noop_span_swallows_updates() -> None:
    tracer = NoOpTracer()
    with tracer.span("x", metadata={"a": 1}) as span:
        span.update(output="y", metadata={"b": 2}, model="m", usage={"input": 1, "output": 2})
    tracer.flush()  # no crash


async def test_router_call_passes_through_with_noop() -> None:
    # With the default no-op tracer the router behaves identically (no crash).
    router = ProviderRouter(_settings(), clients={Provider.GROQ: FakeClient()})
    result = await router.complete([ChatMessage(role="user", content="hi")], task_type="fast")
    assert result.text == "ok"


# --- span assertions via mock tracer --------------------------------------------


async def test_router_emits_generation_span() -> None:
    mock = MockTracer()
    router = ProviderRouter(_settings(), clients={Provider.GROQ: FakeClient()}, tracer=mock)  # type: ignore[arg-type]

    await router.complete([ChatMessage(role="user", content="hi")], task_type="smart")

    spans = [s for s in mock.spans if s.name == "llm.complete"]
    assert spans, "router should open an llm.complete span"
    span = spans[0]
    assert span.kind == "generation"
    assert span.metadata is not None and span.metadata["task_type"] == "smart"
    last = span.updates[-1]
    assert last["usage"] == {"input": 11, "output": 7}
    assert last["metadata"]["provider"] == "groq"


async def test_run_turn_emits_turn_span(tmp_path: Path) -> None:
    mock = MockTracer()
    graph = build_graph(
        router=FakeRouter(),  # type: ignore[arg-type]
        profile_store=ProfileStore(base_path=str(tmp_path)),
    )
    await run_turn(graph, "t1", "hello", tracer=mock)  # type: ignore[arg-type]

    turn = [s for s in mock.spans if s.name == "orchestrator.turn"]
    assert turn, "run_turn should open an orchestrator.turn span"
    last = turn[0].updates[-1]
    assert last["metadata"]["intent"] == "general"
    assert last["metadata"]["active_agent"] == "general"

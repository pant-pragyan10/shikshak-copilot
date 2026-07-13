"""Observability / tracing (Phase 7).

Langfuse is funnelled through this one module — no other file imports the Langfuse
SDK, mirroring the provider-router discipline (so it stays swappable). Callers use a
tiny, provider-agnostic surface:

    tracer = get_tracer()
    with tracer.span("llm.complete", kind="generation", metadata={"task_type": "fast"}) as span:
        ...
        span.update(model=..., usage={"input": n, "output": m}, output=text)

**Tracing never breaks the app.** When Langfuse isn't configured (or fails to init),
``get_tracer`` returns a :class:`NoOpTracer` whose spans do nothing, so the app runs
identically with or without observability. Every Langfuse interaction is also wrapped
defensively — a tracing error is logged and swallowed, never propagated.

Nesting is automatic: Langfuse spans use OpenTelemetry context, so a router
``llm.complete`` span opened inside an ``orchestrator.turn`` span nests under it.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Literal, Protocol, runtime_checkable

from teacher_copilot.config import get_settings

logger = logging.getLogger("teacher_copilot.observability")

SpanKind = Literal["span", "generation"]


@runtime_checkable
class Span(Protocol):
    """A trace span. A context manager; ``update`` enriches it with results."""

    def update(
        self,
        *,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        usage: dict[str, int] | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None: ...

    def __enter__(self) -> Span: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


@runtime_checkable
class Tracer(Protocol):
    """Creates spans and flushes buffered traces."""

    def span(
        self, name: str, *, kind: SpanKind = "span", metadata: dict[str, Any] | None = None
    ) -> Span: ...

    def flush(self) -> None: ...


# --- no-op (default when Langfuse is unconfigured) ------------------------------


class _NoOpSpan:
    def update(
        self,
        *,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        usage: dict[str, int] | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        return None

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class NoOpTracer:
    """Does nothing. The app behaves identically to having no tracing at all."""

    def span(
        self, name: str, *, kind: SpanKind = "span", metadata: dict[str, Any] | None = None
    ) -> _NoOpSpan:
        return _NoOpSpan()

    def flush(self) -> None:
        return None


# --- Langfuse-backed ------------------------------------------------------------


class _LangfuseSpan:
    """Wraps a Langfuse observation context manager; all SDK calls are guarded."""

    def __init__(self, cm: Any) -> None:
        self._cm = cm
        self._span: Any = None

    def __enter__(self) -> _LangfuseSpan:
        try:
            self._span = self._cm.__enter__()
        except Exception as exc:  # never let tracing break the traced code
            logger.debug("langfuse span enter failed: %s", exc)
            self._span = None
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            self._cm.__exit__(exc_type, exc, tb)
        except Exception as err:
            logger.debug("langfuse span exit failed: %s", err)

    def update(
        self,
        *,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        usage: dict[str, int] | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        if self._span is None:
            return
        fields: dict[str, Any] = {}
        if output is not None:
            fields["output"] = output
        if metadata is not None:
            fields["metadata"] = metadata
        if model is not None:
            fields["model"] = model
        if usage is not None:
            fields["usage_details"] = usage
        if level is not None:
            fields["level"] = level
        if status_message is not None:
            fields["status_message"] = status_message
        try:
            self._span.update(**fields)
        except Exception as err:
            logger.debug("langfuse span update failed: %s", err)


class LangfuseTracer:
    """Emits spans to Langfuse. Constructed only when Langfuse is configured."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def span(
        self, name: str, *, kind: SpanKind = "span", metadata: dict[str, Any] | None = None
    ) -> _LangfuseSpan:
        try:
            cm = self._client.start_as_current_observation(
                name=name,
                as_type="generation" if kind == "generation" else "span",
                metadata=metadata,
            )
            return _LangfuseSpan(cm)
        except Exception as exc:
            logger.debug("langfuse span create failed: %s", exc)
            return _LangfuseSpan(_NullCM())

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception as exc:
            logger.debug("langfuse flush failed: %s", exc)


class _NullCM:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_: object) -> None:
        return None


@lru_cache(maxsize=1)
def get_tracer() -> Tracer:
    """Return the process-wide tracer — Langfuse if configured, else a no-op."""
    settings = get_settings()
    if not settings.langfuse_configured:
        return NoOpTracer()
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse tracing enabled (host=%s).", settings.langfuse_host)
        return LangfuseTracer(client)
    except Exception as exc:  # SDK missing / bad keys — degrade to no-op, don't crash
        logger.warning("Langfuse init failed; tracing disabled: %s", exc)
        return NoOpTracer()

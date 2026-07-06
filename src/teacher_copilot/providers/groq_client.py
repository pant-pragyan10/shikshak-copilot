"""Groq provider client (Phase 1).

Async wrapper over the official ``groq`` SDK (``AsyncGroq``) for fast text inference.
Only the router imports this module. SDK exceptions are mapped onto the shared
:mod:`teacher_copilot.providers.errors` hierarchy.
"""

from __future__ import annotations

import time
from typing import Any

import groq
from groq import AsyncGroq

from teacher_copilot.providers.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderModelNotFoundError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from teacher_copilot.providers.types import ChatMessage, CompletionResult, Provider

DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Substrings Groq uses when a model id is unknown or retired.
_MODEL_ERROR_HINTS = ("model_not_found", "does not exist", "decommission", "not found")


def _looks_like_model_error(exc: groq.APIStatusError) -> bool:
    """True if a 4xx error is really about the model id (unknown / decommissioned)."""
    text = str(exc).lower()
    return "model" in text and any(hint in text for hint in _MODEL_ERROR_HINTS)


def _is_json_validate_failed(exc: groq.APIStatusError) -> bool:
    """True when Groq rejected strict json_object mode (common with gpt-oss models).

    These reasoning models emit a bit of prose around the JSON, which Groq's
    server-side ``json_object`` validator rejects with ``json_validate_failed``. The
    fix is to retry without ``response_format`` and let the caller's ``extract_json``
    recover the object from the free-form text.
    """
    return "json_validate_failed" in str(exc).lower()


def _retry_after_seconds(exc: groq.APIStatusError) -> float | None:
    """Best-effort extraction of a ``retry-after`` header (seconds) from an error."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class GroqClient:
    """Async client for Groq chat completions."""

    provider = Provider.GROQ

    def __init__(self, api_key: str, *, default_model: str = DEFAULT_MODEL) -> None:
        self.default_model = default_model
        self._client = AsyncGroq(api_key=api_key)

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        """Call Groq and return a normalised :class:`CompletionResult`.

        Groq is text-only here: image parts (if any) are flattened to their text.
        """
        used_model = model or self.default_model
        payload = [{"role": m.role, "content": m.as_text()} for m in messages]
        kwargs: dict[str, Any] = {
            "model": used_model,
            "messages": payload,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            response = await self._create(kwargs)
        except groq.RateLimitError as exc:
            raise ProviderRateLimitError(
                str(exc), provider=self.provider, retry_after=_retry_after_seconds(exc)
            ) from exc
        except groq.AuthenticationError as exc:
            raise ProviderAuthError(str(exc), provider=self.provider) from exc
        except groq.NotFoundError as exc:
            raise ProviderModelNotFoundError(used_model, provider=self.provider) from exc
        except (groq.APIConnectionError, groq.InternalServerError) as exc:
            raise ProviderUnavailableError(str(exc), provider=self.provider) from exc
        except groq.APIStatusError as exc:
            # Any other non-2xx: model-churn errors first, then 5xx transient, else hard.
            if _looks_like_model_error(exc):
                raise ProviderModelNotFoundError(used_model, provider=self.provider) from exc
            if exc.status_code >= 500:
                raise ProviderUnavailableError(str(exc), provider=self.provider) from exc
            raise ProviderError(str(exc), provider=self.provider) from exc
        latency_ms = (time.perf_counter() - started) * 1000

        text = response.choices[0].message.content or ""
        usage = response.usage
        return CompletionResult(
            text=text,
            provider=self.provider,
            model=used_model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
        )

    async def _create(self, kwargs: dict[str, Any]) -> Any:
        """Create a completion, degrading gracefully out of strict JSON mode.

        If Groq rejects ``response_format=json_object`` (``json_validate_failed``),
        retry once as free-form text. The caller recovers the JSON via extract_json.
        """
        try:
            return await self._client.chat.completions.create(**kwargs)
        except groq.APIStatusError as exc:
            if "response_format" in kwargs and _is_json_validate_failed(exc):
                relaxed = {k: v for k, v in kwargs.items() if k != "response_format"}
                return await self._client.chat.completions.create(**relaxed)
            raise

    async def reachable(self) -> bool:
        """Configured Groq clients are assumed reachable (avoid burning quota to probe)."""
        return True

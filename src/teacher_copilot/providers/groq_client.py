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
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from teacher_copilot.providers.types import ChatMessage, CompletionResult, Provider

DEFAULT_MODEL = "llama-3.3-70b-versatile"


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
            response = await self._client.chat.completions.create(**kwargs)
        except groq.RateLimitError as exc:
            raise ProviderRateLimitError(
                str(exc), provider=self.provider, retry_after=_retry_after_seconds(exc)
            ) from exc
        except groq.AuthenticationError as exc:
            raise ProviderAuthError(str(exc), provider=self.provider) from exc
        except (groq.APIConnectionError, groq.InternalServerError) as exc:
            raise ProviderUnavailableError(str(exc), provider=self.provider) from exc
        except groq.APIStatusError as exc:
            # Any other non-2xx: treat 5xx as transient, everything else as a hard error.
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

    async def reachable(self) -> bool:
        """Configured Groq clients are assumed reachable (avoid burning quota to probe)."""
        return True

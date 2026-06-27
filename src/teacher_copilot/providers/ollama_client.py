"""Ollama provider client (Phase 1).

Plain ``httpx`` client against a local Ollama server — no SDK dependency. This is
the last-resort fallback so the system degrades gracefully when both hosted free
tiers are rate-limited. A connection refusal maps to
:class:`ProviderUnavailableError` so the router skips it rather than crashing.
"""

from __future__ import annotations

import time

import httpx

from teacher_copilot.providers.errors import (
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from teacher_copilot.providers.types import ChatMessage, CompletionResult, Provider

DEFAULT_MODEL = "llama3.2:3b"


class OllamaClient:
    """Async client for a local Ollama server (REST ``/api/chat``)."""

    provider = Provider.OLLAMA

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        *,
        default_model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
    ) -> None:
        self.default_model = default_model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        """Call the local Ollama server and return a normalised result (text-only)."""
        used_model = model or self.default_model
        payload = {
            "model": used_model,
            "messages": [{"role": m.role, "content": m.as_text()} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                f"Ollama not reachable at {self._base_url}", provider=self.provider
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                raise ProviderRateLimitError(str(exc), provider=self.provider) from exc
            if status >= 500:
                raise ProviderUnavailableError(str(exc), provider=self.provider) from exc
            raise ProviderError(str(exc), provider=self.provider) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc), provider=self.provider) from exc
        latency_ms = (time.perf_counter() - started) * 1000

        data = response.json()
        text = data.get("message", {}).get("content", "")
        return CompletionResult(
            text=text,
            provider=self.provider,
            model=used_model,
            input_tokens=int(data.get("prompt_eval_count", 0) or 0),
            output_tokens=int(data.get("eval_count", 0) or 0),
            latency_ms=latency_ms,
        )

    async def reachable(self) -> bool:
        """Quick liveness probe: GET the Ollama root. False on any connection error."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=2.0) as client:
                response = await client.get("/")
                return response.status_code < 500
        except httpx.HTTPError:
            return False

"""Gemini provider client (Phase 1).

Async wrapper over the ``google-genai`` SDK (``Client.aio``). This is the only
multimodal-capable provider — image parts (scanned answers, Phase 3) route here.
Only the router imports this module. SDK exceptions map onto the shared
:mod:`teacher_copilot.providers.errors` hierarchy.
"""

from __future__ import annotations

import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from teacher_copilot.providers.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from teacher_copilot.providers.types import (
    ChatMessage,
    CompletionResult,
    ImagePart,
    Provider,
    TextPart,
)

# gemini-2.0-flash carries the most generous free-tier daily request/token budget of
# the flash-class models, which is why it is the default. Overridable per call.
DEFAULT_MODEL = "gemini-2.0-flash"

# Gemini uses "model" (not "assistant") for its own turns; system turns are hoisted
# into a separate system_instruction.
_ROLE_MAP = {"assistant": "model", "user": "user", "model": "model"}


def _to_parts(message: ChatMessage) -> list[types.Part]:
    """Convert a ChatMessage's content into google-genai parts."""
    if isinstance(message.content, str):
        return [types.Part.from_text(text=message.content)]
    parts: list[types.Part] = []
    for part in message.content:
        if isinstance(part, TextPart):
            parts.append(types.Part.from_text(text=part.text))
        elif isinstance(part, ImagePart):
            parts.append(types.Part.from_bytes(data=part.data, mime_type=part.mime_type))
    return parts


def _split_messages(
    messages: list[ChatMessage],
) -> tuple[list[types.Content], str | None]:
    """Split into (conversation contents, system instruction)."""
    system_chunks: list[str] = []
    contents: list[types.Content] = []
    for message in messages:
        if message.role == "system":
            system_chunks.append(message.as_text())
            continue
        role = _ROLE_MAP.get(message.role, "user")
        contents.append(types.Content(role=role, parts=_to_parts(message)))
    system_instruction = "\n".join(system_chunks) if system_chunks else None
    return contents, system_instruction


class GeminiClient:
    """Async client for Gemini chat / multimodal completions."""

    provider = Provider.GEMINI

    def __init__(self, api_key: str, *, default_model: str = DEFAULT_MODEL) -> None:
        self.default_model = default_model
        self._client = genai.Client(api_key=api_key)

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        """Call Gemini (text or multimodal) and return a normalised result."""
        used_model = model or self.default_model
        contents, system_instruction = _split_messages(messages)
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
            response_mime_type="application/json" if json_mode else None,
        )

        started = time.perf_counter()
        try:
            response = await self._client.aio.models.generate_content(
                model=used_model, contents=contents, config=config
            )
        except genai_errors.APIError as exc:
            raise self._map_error(exc) from exc
        latency_ms = (time.perf_counter() - started) * 1000

        usage = response.usage_metadata
        return CompletionResult(
            text=response.text or "",
            provider=self.provider,
            model=used_model,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            latency_ms=latency_ms,
        )

    def _map_error(self, exc: genai_errors.APIError) -> ProviderError:
        """Map a google-genai APIError onto the shared error hierarchy by status code."""
        code = getattr(exc, "code", None)
        message = getattr(exc, "message", None) or str(exc)
        if code == 429:
            return ProviderRateLimitError(message, provider=self.provider)
        if code in (401, 403):
            return ProviderAuthError(message, provider=self.provider)
        if code is not None and code >= 500:
            return ProviderUnavailableError(message, provider=self.provider)
        if isinstance(exc, genai_errors.ServerError):
            return ProviderUnavailableError(message, provider=self.provider)
        return ProviderError(message, provider=self.provider)

    async def reachable(self) -> bool:
        """Configured Gemini clients are assumed reachable (avoid burning quota to probe)."""
        return True

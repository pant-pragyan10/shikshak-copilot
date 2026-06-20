"""Provider routing layer (Phase 1).

The one gateway for every external LLM call. Responsibilities (Phase 1):
    * pick a provider by capability (text vs. multimodal) and availability,
    * fall back Groq -> Gemini -> Ollama on rate limits / errors,
    * retry with backoff on 429s, and
    * consult the response cache before calling out.

No module outside this package may import a provider SDK directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from enum import StrEnum

from pydantic import BaseModel, Field


class Provider(StrEnum):
    """Known LLM providers, in default fallback priority order."""

    GROQ = "groq"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class ChatMessage(BaseModel):
    """A provider-agnostic chat message."""

    role: str = Field(description="user | assistant | system.")
    content: str = Field(description="Message text.")


class CompletionResult(BaseModel):
    """Normalised completion result returned by the router."""

    text: str = Field(description="Generated text.")
    provider: Provider = Field(description="Provider that served the request.")
    model: str = Field(description="Concrete model id used.")
    cached: bool = Field(default=False, description="Whether served from cache.")


class ProviderRouter:
    """Routes LLM requests across providers with fallback, retry, and caching."""

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        multimodal: bool = False,
    ) -> CompletionResult:
        """Return a completion, choosing a provider and handling fallback/caching.

        Args:
            messages: Conversation to complete.
            multimodal: If True, require a vision-capable provider (Gemini).

        Returns:
            A normalised :class:`CompletionResult`.
        """
        raise NotImplementedError("Phase 1")

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        multimodal: bool = False,
    ) -> AsyncIterator[str]:
        """Stream a completion as text chunks. See :meth:`complete`."""
        raise NotImplementedError("Phase 1")

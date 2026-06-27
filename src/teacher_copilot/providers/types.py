"""Shared provider types: messages, results, task types, and the client protocol.

These live in their own module (rather than ``router.py``) so the concrete provider
clients and the router can both import them without a circular dependency. For
backward compatibility, ``router.py`` re-exports :class:`Provider`,
:class:`ChatMessage`, and :class:`CompletionResult`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Provider(StrEnum):
    """Known LLM providers."""

    GROQ = "groq"
    GEMINI = "gemini"
    OLLAMA = "ollama"


#: Routing categories. Each maps to an ordered provider chain in the router.
TaskType = Literal["fast", "multimodal", "bulk"]


class TextPart(BaseModel):
    """A text fragment of a multimodal message."""

    type: Literal["text"] = "text"
    text: str = Field(description="Text content.")


class ImagePart(BaseModel):
    """An inline image fragment of a multimodal message (e.g. a scanned answer)."""

    type: Literal["image"] = "image"
    data: bytes = Field(description="Raw image bytes.")
    mime_type: str = Field(default="image/png", description="Image MIME type.")


#: A single piece of message content.
ContentPart = TextPart | ImagePart


class ChatMessage(BaseModel):
    """A provider-agnostic chat message.

    ``content`` is either a plain string (the common, backward-compatible case) or a
    list of parts for multimodal input. Text-only providers use :meth:`as_text`;
    multimodal providers inspect the parts directly.
    """

    role: str = Field(description="user | assistant | system.")
    content: str | list[ContentPart] = Field(description="Text, or multimodal parts.")

    def has_images(self) -> bool:
        """True if this message carries any image part."""
        if isinstance(self.content, str):
            return False
        return any(isinstance(part, ImagePart) for part in self.content)

    def as_text(self) -> str:
        """Flatten to text, dropping image parts (for text-only providers)."""
        if isinstance(self.content, str):
            return self.content
        return "\n".join(part.text for part in self.content if isinstance(part, TextPart))


def messages_have_images(messages: list[ChatMessage]) -> bool:
    """True if any message in the list carries an image part."""
    return any(m.has_images() for m in messages)


class CompletionResult(BaseModel):
    """Normalised completion result returned by every provider client and the router."""

    text: str = Field(description="Generated text.")
    provider: Provider = Field(description="Provider that served the request.")
    model: str = Field(description="Concrete model id used.")
    input_tokens: int = Field(default=0, ge=0, description="Prompt tokens consumed.")
    output_tokens: int = Field(default=0, ge=0, description="Completion tokens produced.")
    latency_ms: float = Field(default=0.0, ge=0, description="Wall-clock call latency (ms).")
    cached: bool = Field(default=False, description="Whether served from the response cache.")


@runtime_checkable
class ProviderClient(Protocol):
    """Structural interface every provider client satisfies.

    The router depends only on this protocol, which keeps it SDK-agnostic and lets
    tests inject lightweight fakes.
    """

    provider: Provider
    default_model: str

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        """Produce a completion for ``messages``."""
        ...

    async def reachable(self) -> bool:
        """Cheap liveness check that never consumes paid quota."""
        ...

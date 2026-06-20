"""Application configuration.

A single :class:`Settings` object, loaded from environment / ``.env``, is the one
source of truth for provider keys and service URLs. Every provider key is optional
so the app boots without full configuration; code paths that need a given provider
validate its presence at call time (Phase 1+) via the helper properties here.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    """Deployment environment."""

    DEV = "dev"
    PROD = "prod"


class Settings(BaseSettings):
    """Runtime configuration, populated from environment variables / ``.env``.

    All secrets are optional at construction time. Use the ``*_configured``
    properties to gate provider-specific logic instead of assuming a key exists.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---
    env: Env = Field(default=Env.DEV, description="Deployment environment.")

    # --- LLM providers (optional at boot) ---
    groq_api_key: str | None = Field(default=None, description="Groq free-tier API key.")
    gemini_api_key: str | None = Field(
        default=None, description="Google AI Studio (Gemini) API key."
    )
    ollama_url: str = Field(
        default="http://localhost:11434", description="Local Ollama server base URL."
    )

    # --- Vector store ---
    qdrant_url: str = Field(
        default="http://localhost:6333", description="Self-hosted Qdrant base URL."
    )

    # --- Observability (optional; Phase 7) ---
    langfuse_public_key: str | None = Field(default=None)
    langfuse_secret_key: str | None = Field(default=None)
    langfuse_host: str = Field(default="http://localhost:3000")

    @property
    def groq_configured(self) -> bool:
        """True when Groq can be used as a provider."""
        return bool(self.groq_api_key)

    @property
    def gemini_configured(self) -> bool:
        """True when Gemini can be used as a provider."""
        return bool(self.gemini_api_key)

    @property
    def langfuse_configured(self) -> bool:
        """True when both Langfuse keys are present (tracing enabled)."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()

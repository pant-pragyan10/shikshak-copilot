"""Application configuration.

A single :class:`Settings` object, loaded from environment / ``.env``, is the one
source of truth for provider keys and service URLs. Every provider key is optional
so the app boots without full configuration; code paths that need a given provider
validate its presence at call time (Phase 1+) via the helper properties here.
"""

from __future__ import annotations

import warnings
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
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

    # --- Model tiers (per provider, per workload) ---
    # Providers churn model names frequently; every model is an env-overridable
    # default so re-tiering never needs a code change.
    groq_fast_model: str = Field(
        default="openai/gpt-oss-20b",
        description="Groq model for cheap/short calls (intent classification).",
    )
    groq_smart_model: str = Field(
        default="openai/gpt-oss-120b",
        description="Groq model for main agent responses / reasoning-heavy text.",
    )
    # gemini-3.1-flash-lite is the current cost-efficient flash-lite model with the
    # most generous free-tier quota. Google rotates names/quotas — if you hit
    # model-not-found or tighter limits, check AI Studio's rate-limits page and
    # override this via GEMINI_BULK_MODEL: https://ai.google.dev/gemini-api/docs/rate-limits
    gemini_bulk_model: str = Field(
        default="gemini-3.1-flash-lite",
        description="Gemini model for high-volume RAG / lesson-plan synthesis (verify quota).",
    )
    gemini_smart_model: str = Field(
        default="gemini-3.5-flash",
        description="Gemini model for the multimodal grading path.",
    )

    # --- Deprecated single-model vars (mapped onto the smart tier at startup) ---
    groq_model: str | None = Field(
        default=None, description="DEPRECATED: use GROQ_FAST_MODEL / GROQ_SMART_MODEL."
    )
    gemini_model: str | None = Field(
        default=None, description="DEPRECATED: use GEMINI_BULK_MODEL / GEMINI_SMART_MODEL."
    )

    # --- Vector store ---
    # Embedded is the default and the only mode exercised today: QdrantClient(path=...)
    # runs in-process with no server and no Docker. `server` mode (using qdrant_url)
    # is reserved for deployment and is a config switch, not a code change.
    qdrant_mode: Literal["embedded", "server"] = Field(
        default="embedded", description="Qdrant deployment mode."
    )
    qdrant_path: str = Field(
        default="./qdrant_data", description="Embedded-mode on-disk storage directory."
    )
    qdrant_url: str = Field(
        default="http://localhost:6333", description="Server-mode Qdrant base URL (future)."
    )

    # --- Profile store ---
    profile_store_path: str = Field(
        default="./data/profiles", description="Directory of per-teacher JSON profiles."
    )

    # --- Observability (optional; Phase 7) ---
    langfuse_public_key: str | None = Field(default=None)
    langfuse_secret_key: str | None = Field(default=None)
    langfuse_host: str = Field(default="http://localhost:3000")

    @model_validator(mode="after")
    def _map_deprecated_models(self) -> Settings:
        """Map legacy single-model env vars onto the smart tier, warning loudly."""
        if self.groq_model:
            warnings.warn(
                "GROQ_MODEL is deprecated; mapping it onto GROQ_SMART_MODEL. "
                "Set GROQ_FAST_MODEL / GROQ_SMART_MODEL instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.groq_smart_model = self.groq_model
        if self.gemini_model:
            warnings.warn(
                "GEMINI_MODEL is deprecated; mapping it onto GEMINI_SMART_MODEL. "
                "Set GEMINI_BULK_MODEL / GEMINI_SMART_MODEL instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.gemini_smart_model = self.gemini_model
        return self

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

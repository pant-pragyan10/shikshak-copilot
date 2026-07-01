"""Provider error hierarchy.

Provider SDKs raise heterogeneous exceptions; each client maps them onto this small,
stable hierarchy so the router can reason about failures uniformly.
"""

from __future__ import annotations

from teacher_copilot.providers.types import Provider


class ProviderError(Exception):
    """Base class for all provider failures."""

    def __init__(self, message: str, *, provider: Provider | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class ProviderRateLimitError(ProviderError):
    """The provider returned HTTP 429 (rate / quota limit).

    ``retry_after`` carries the server-suggested wait in seconds, when present.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: Provider | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider)
        self.retry_after = retry_after


class ProviderAuthError(ProviderError):
    """Authentication/authorization failed (bad or missing key). Not retryable."""


class ProviderUnavailableError(ProviderError):
    """The provider is unreachable or returned a transient server error (5xx / connection)."""


class ProviderModelNotFoundError(ProviderError):
    """The requested model does not exist on the provider (likely deprecated/renamed).

    The router treats this like :class:`ProviderUnavailableError` (fall back to the
    next provider), but the message names the offending model so the operator can fix
    the corresponding env var.
    """

    def __init__(self, model: str, *, provider: Provider | None = None) -> None:
        self.model = model
        message = (
            f"Model '{model}' not found on provider '{provider}'. The provider may have "
            "deprecated this model — check the provider's deprecations page and update the "
            "corresponding env var."
        )
        super().__init__(message, provider=provider)


class ProviderExhaustedError(ProviderError):
    """Every provider in the routing chain failed.

    ``failures`` maps each attempted provider to a human-readable reason, for logging
    and for the friendly "system busy" message the API layer builds in Phase 6.
    """

    def __init__(self, message: str, *, failures: dict[Provider, str] | None = None) -> None:
        super().__init__(message)
        self.failures = failures or {}

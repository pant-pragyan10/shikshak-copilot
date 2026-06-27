"""Provider routing layer (Phase 1) — the single gateway for every LLM call.

No module outside this package may import a provider SDK directly; they all call
:class:`ProviderRouter`. The router turns free-tier rate limits into a first-class,
declarative concern: an explicit routing table maps a *task type* to an ordered
provider chain, and the router walks that chain with retry-then-fallback semantics.

Scaling the system means editing the table / tiers below — not touching any caller.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from teacher_copilot.config import Settings
from teacher_copilot.providers.cache import ResponseCache
from teacher_copilot.providers.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderExhaustedError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from teacher_copilot.providers.gemini_client import GeminiClient
from teacher_copilot.providers.groq_client import GroqClient
from teacher_copilot.providers.ollama_client import OllamaClient
from teacher_copilot.providers.types import (
    ChatMessage,
    CompletionResult,
    Provider,
    ProviderClient,
    TaskType,
    messages_have_images,
)

# Re-export the shared models so existing imports (`from ...router import ...`) hold.
__all__ = [
    "ChatMessage",
    "CompletionResult",
    "Provider",
    "ProviderRouter",
    "ROUTING_TABLE",
]

logger = logging.getLogger("teacher_copilot.providers")

# --- Routing policy -------------------------------------------------------------
# Explicit and declarative on purpose (not buried in if/else). Each task type maps
# to an ordered provider chain; the router tries them left-to-right on failure.
#
#   fast       chat / intent / wellbeing — latency matters   -> Groq first
#   multimodal image inputs (grading)    — Gemini only        -> no text fallback
#   bulk       lesson-plan / career RAG  — big token budget   -> Gemini first
ROUTING_TABLE: dict[TaskType, tuple[Provider, ...]] = {
    "fast": (Provider.GROQ, Provider.GEMINI, Provider.OLLAMA),
    "multimodal": (Provider.GEMINI,),
    "bulk": (Provider.GEMINI, Provider.GROQ, Provider.OLLAMA),
}

# Retry budget: at most one retry per provider; total sleep across the whole call
# is capped so a caller never blocks longer than this.
_MAX_TOTAL_WAIT_SECONDS = 10.0
_RETRY_BASE_BACKOFF_SECONDS = 0.5


class ProviderRouter:
    """Routes LLM requests across providers with fallback, retry, and caching."""

    def __init__(
        self,
        settings: Settings,
        *,
        clients: dict[Provider, ProviderClient] | None = None,
        cache: ResponseCache | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_total_wait: float = _MAX_TOTAL_WAIT_SECONDS,
    ) -> None:
        self._settings = settings
        self._clients: dict[Provider, ProviderClient] = (
            clients if clients is not None else self._build_clients(settings)
        )
        self._cache = cache if cache is not None else ResponseCache()
        self._sleep = sleep
        self._max_total_wait = max_total_wait
        # Providers disabled for the rest of the process after an auth failure — a
        # bad key never fixes itself mid-run, so stop retrying it.
        self._disabled: set[Provider] = set()

    @staticmethod
    def _build_clients(settings: Settings) -> dict[Provider, ProviderClient]:
        """Instantiate only the clients whose configuration is present."""
        clients: dict[Provider, ProviderClient] = {}
        if settings.groq_api_key:
            clients[Provider.GROQ] = GroqClient(settings.groq_api_key)
        if settings.gemini_api_key:
            clients[Provider.GEMINI] = GeminiClient(settings.gemini_api_key)
        # Ollama has no key; it is always a candidate (reachability decided at call time).
        clients[Provider.OLLAMA] = OllamaClient(settings.ollama_url)
        return clients

    @property
    def cache(self) -> ResponseCache:
        """The response cache (exposes ``.stats()`` for tracing in Phase 7)."""
        return self._cache

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        task_type: TaskType = "fast",
        cacheable: bool = False,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        """Complete ``messages``, choosing a provider per the routing table.

        Falls back down the chain on rate-limit / unavailability, retries once per
        provider (honouring ``retry_after``), and consults the cache when
        ``cacheable`` is set. Raises :class:`ProviderExhaustedError` if all fail.
        """
        # Image inputs force the multimodal chain regardless of the caller's task_type,
        # so text-only providers never silently drop a scanned answer.
        effective_task: TaskType = "multimodal" if messages_have_images(messages) else task_type
        chain = ROUTING_TABLE[effective_task]

        cache_key: str | None = None
        if cacheable:
            cache_key = self._cache.make_key(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            hit = await self._cache.get(cache_key)
            if hit is not None:
                logger.info("cache hit provider=%s model=%s", hit.provider, hit.model)
                return hit
            logger.debug("cache miss key=%s", cache_key[:12])

        failures: dict[Provider, str] = {}
        wait_budget = self._max_total_wait

        for provider in chain:
            client = self._clients.get(provider)
            if client is None:
                failures[provider] = "not configured"
                continue
            if provider in self._disabled:
                failures[provider] = "disabled (auth failure earlier this run)"
                continue

            result, reason, wait_budget = await self._try_provider(
                client,
                provider,
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                wait_budget=wait_budget,
            )
            if result is not None:
                if failures:
                    logger.info(
                        "served by %s after fallbacks=%s", provider, list(failures)
                    )
                else:
                    logger.info(
                        "served by %s model=%s latency_ms=%.0f",
                        provider,
                        result.model,
                        result.latency_ms,
                    )
                if cache_key is not None:
                    await self._cache.set(cache_key, result)
                return result

            failures[provider] = reason or "unknown error"
            logger.warning("provider %s failed: %s — falling back", provider, failures[provider])

        raise ProviderExhaustedError(
            f"All providers exhausted for task_type={effective_task}: {failures}",
            failures=failures,
        )

    async def _try_provider(
        self,
        client: ProviderClient,
        provider: Provider,
        messages: list[ChatMessage],
        *,
        model: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        wait_budget: float,
    ) -> tuple[CompletionResult | None, str | None, float]:
        """Attempt one provider with a single transient retry.

        Returns ``(result, failure_reason, remaining_wait_budget)``. ``result`` is
        None when the provider should be skipped/fallen-back-from.
        """
        for attempt in range(2):  # initial try + one retry
            try:
                result = await client.complete(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
                return result, None, wait_budget
            except ProviderAuthError as exc:
                self._disabled.add(provider)
                logger.error(
                    "auth failure on %s — disabling for process lifetime: %s", provider, exc
                )
                return None, f"auth error: {exc}", wait_budget
            except (ProviderRateLimitError, ProviderUnavailableError) as exc:
                if attempt >= 1:
                    return None, str(exc), wait_budget  # already retried; fall back
                retry_after = getattr(exc, "retry_after", None)
                wait = retry_after if retry_after is not None else _RETRY_BASE_BACKOFF_SECONDS
                wait = min(wait, wait_budget)
                if wait <= 0:
                    return None, f"{exc} (retry budget exhausted)", wait_budget
                logger.info("retrying %s in %.2fs after transient error", provider, wait)
                await self._sleep(wait)
                wait_budget -= wait
            except ProviderError as exc:
                return None, str(exc), wait_budget  # hard, non-transient error
        return None, "retries exhausted", wait_budget

    async def health(self) -> dict[str, dict[str, bool]]:
        """Report which providers are configured / reachable.

        Only Ollama is actively probed (a cheap local GET). Hosted providers report
        configuration only — pinging them would burn free-tier quota.
        """
        report: dict[str, dict[str, bool]] = {}
        for provider in Provider:
            client = self._clients.get(provider)
            entry: dict[str, bool] = {
                "configured": client is not None,
                "disabled": provider in self._disabled,
            }
            if provider is Provider.OLLAMA and client is not None:
                entry["reachable"] = await client.reachable()
            report[provider.value] = entry
        return report

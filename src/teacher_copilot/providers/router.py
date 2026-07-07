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
from enum import StrEnum
from functools import lru_cache

from teacher_copilot.config import Settings, get_settings
from teacher_copilot.observability.tracing import Tracer, get_tracer
from teacher_copilot.providers.cache import ResponseCache
from teacher_copilot.providers.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderExhaustedError,
    ProviderModelNotFoundError,
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
    "get_router",
]

logger = logging.getLogger("teacher_copilot.providers")

class ModelTier(StrEnum):
    """A (provider, workload) slot whose concrete model id comes from Settings.

    Keeping the table in terms of tiers — not literal model strings — means model
    churn is an env-var/Settings change, never a code change here.
    """

    GROQ_FAST = "groq_fast"
    GROQ_SMART = "groq_smart"
    GEMINI_BULK = "gemini_bulk"
    GEMINI_SMART = "gemini_smart"
    OLLAMA_DEFAULT = "ollama_default"  # use the Ollama client's own default model


# --- Routing policy -------------------------------------------------------------
# Explicit and declarative on purpose (not buried in if/else). Each task type maps
# to an ordered chain of (provider, model tier); the router tries them left-to-right
# on failure. A per-call `model=` override always wins over the tier below.
#
#   fast       intent / short cheap calls        -> Groq(fast)  -> Gemini(bulk) -> Ollama
#   smart      reasoning-heavy text (grading FB)  -> Groq(smart) -> Gemini(smart)-> Ollama
#   multimodal image inputs (scanned grading)     -> Gemini(smart) only, no fallback
#   bulk       lesson-plan / career RAG synthesis -> Gemini(bulk) -> Groq(smart) -> Ollama
ROUTING_TABLE: dict[TaskType, tuple[tuple[Provider, ModelTier], ...]] = {
    "fast": (
        (Provider.GROQ, ModelTier.GROQ_FAST),
        (Provider.GEMINI, ModelTier.GEMINI_BULK),
        (Provider.OLLAMA, ModelTier.OLLAMA_DEFAULT),
    ),
    "smart": (
        (Provider.GROQ, ModelTier.GROQ_SMART),
        (Provider.GEMINI, ModelTier.GEMINI_SMART),
        (Provider.OLLAMA, ModelTier.OLLAMA_DEFAULT),
    ),
    "multimodal": ((Provider.GEMINI, ModelTier.GEMINI_SMART),),
    "bulk": (
        (Provider.GEMINI, ModelTier.GEMINI_BULK),
        (Provider.GROQ, ModelTier.GROQ_SMART),
        (Provider.OLLAMA, ModelTier.OLLAMA_DEFAULT),
    ),
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
        tracer: Tracer | None = None,
    ) -> None:
        self._settings = settings
        self._clients: dict[Provider, ProviderClient] = (
            clients if clients is not None else self._build_clients(settings)
        )
        self._cache = cache if cache is not None else ResponseCache()
        self._sleep = sleep
        self._max_total_wait = max_total_wait
        # Tracing is funnelled through observability/; defaults to a no-op unless
        # Langfuse is configured. The router never hard-depends on Langfuse.
        self._tracer = tracer if tracer is not None else get_tracer()
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

    def _resolve_model(self, tier: ModelTier) -> str | None:
        """Resolve a model tier to a concrete model id from Settings.

        ``OLLAMA_DEFAULT`` returns None so the Ollama client uses its own default.
        """
        s = self._settings
        table: dict[ModelTier, str | None] = {
            ModelTier.GROQ_FAST: s.groq_fast_model,
            ModelTier.GROQ_SMART: s.groq_smart_model,
            ModelTier.GEMINI_BULK: s.gemini_bulk_model,
            ModelTier.GEMINI_SMART: s.gemini_smart_model,
            ModelTier.OLLAMA_DEFAULT: None,
        }
        return table[tier]

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
        validate: Callable[[CompletionResult], bool] | None = None,
    ) -> CompletionResult:
        """Complete ``messages``, choosing a provider per the routing table.

        Falls back down the chain on rate-limit / unavailability, retries once per
        provider (honouring ``retry_after``), and consults the cache when
        ``cacheable`` is set. Raises :class:`ProviderExhaustedError` if all fail.

        ``validate`` lets a caller gate caching on its own success criterion (e.g. "the
        JSON parses into my schema"). A response that fails ``validate`` is never
        written to the cache, and an existing cached entry that fails it is treated as a
        miss and regenerated — so one malformed completion can't poison a key forever.
        """
        # Image inputs force the multimodal chain regardless of the caller's task_type,
        # so text-only providers never silently drop a scanned answer.
        effective_task: TaskType = "multimodal" if messages_have_images(messages) else task_type
        chain = ROUTING_TABLE[effective_task]

        # One span per LLM call makes the free-tier routing visible: provider chosen,
        # model/tier, fallbacks taken, cache hit/miss, tokens, latency (see docstring).
        with self._tracer.span(
            "llm.complete",
            kind="generation",
            metadata={"task_type": effective_task, "cacheable": cacheable},
        ) as span:
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
                if hit is not None and (validate is None or validate(hit)):
                    logger.info("cache hit provider=%s model=%s", hit.provider, hit.model)
                    span.update(
                        model=hit.model,
                        metadata={"provider": str(hit.provider), "cache": "hit"},
                    )
                    return hit
                if hit is not None:
                    logger.info("cached response failed validation, regenerating")
                logger.debug("cache miss key=%s", cache_key[:12])

            failures: dict[Provider, str] = {}
            wait_budget = self._max_total_wait

            for provider, tier in chain:
                client = self._clients.get(provider)
                if client is None:
                    failures[provider] = "not configured"
                    continue
                if provider in self._disabled:
                    failures[provider] = "disabled (auth failure earlier this run)"
                    continue

                # Per-call override wins over the routing table's tier.
                chosen_model = model if model is not None else self._resolve_model(tier)
                result, reason, wait_budget = await self._try_provider(
                    client,
                    provider,
                    messages,
                    model=chosen_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    wait_budget=wait_budget,
                )
                if result is not None:
                    if failures:
                        logger.info("served by %s after fallbacks=%s", provider, list(failures))
                    else:
                        logger.info(
                            "served by %s model=%s latency_ms=%.0f",
                            provider,
                            result.model,
                            result.latency_ms,
                        )
                    if cache_key is not None and (validate is None or validate(result)):
                        await self._cache.set(cache_key, result)
                    span.update(
                        model=result.model,
                        output=result.text[:500],
                        usage={"input": result.input_tokens, "output": result.output_tokens},
                        metadata={
                            "provider": str(result.provider),
                            "cache": "miss" if cacheable else "off",
                            "latency_ms": round(result.latency_ms, 1),
                            "fallbacks": [str(p) for p in failures],
                        },
                    )
                    return result

                failures[provider] = reason or "unknown error"
                logger.warning(
                    "provider %s failed: %s — falling back", provider, failures[provider]
                )

            span.update(
                level="ERROR",
                status_message="all providers exhausted",
                metadata={"failures": {str(k): v for k, v in failures.items()}},
            )
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
            except ProviderModelNotFoundError as exc:
                # Model churn: no point retrying the same missing model — fall back
                # immediately, but log the operator-facing guidance loudly.
                logger.warning("model unavailable on %s — falling back: %s", provider, exc)
                return None, str(exc), wait_budget
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


@lru_cache(maxsize=1)
def get_router() -> ProviderRouter:
    """Return the process-wide :class:`ProviderRouter` (built from cached settings).

    Construction is cheap and makes no network calls; provider clients are only
    exercised when :meth:`ProviderRouter.complete` is invoked.
    """
    return ProviderRouter(get_settings())

"""Provider routing tests — fully mocked, no network, no real SDK calls."""

from __future__ import annotations

import os

import pytest

from teacher_copilot.config import Settings
from teacher_copilot.providers.errors import (
    ProviderAuthError,
    ProviderExhaustedError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from teacher_copilot.providers.router import ProviderRouter
from teacher_copilot.providers.types import (
    ChatMessage,
    CompletionResult,
    ImagePart,
    Provider,
)


class FakeClient:
    """A stand-in provider client driven by a scripted list of per-call behaviours."""

    def __init__(
        self,
        provider: Provider,
        *,
        behaviors: list[Exception | None] | None = None,
        default_model: str = "fake-model",
    ) -> None:
        self.provider = provider
        self.default_model = default_model
        self._behaviors = list(behaviors or [])
        self.calls = 0

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult:
        idx = self.calls
        self.calls += 1
        if idx < len(self._behaviors):
            behavior = self._behaviors[idx]
            if isinstance(behavior, Exception):
                raise behavior
        return CompletionResult(
            text="ok", provider=self.provider, model=model or self.default_model
        )

    async def reachable(self) -> bool:
        return True


class SleepRecorder:
    """Injectable async sleep that records the durations it was asked to wait."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _msg() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="hello")]


async def test_falls_back_groq_to_gemini_on_rate_limit() -> None:
    groq = FakeClient(Provider.GROQ, behaviors=[ProviderRateLimitError("429")] * 5)
    gemini = FakeClient(Provider.GEMINI)
    sleeper = SleepRecorder()
    router = ProviderRouter(
        _settings(),
        clients={Provider.GROQ: groq, Provider.GEMINI: gemini},
        sleep=sleeper,
    )

    result = await router.complete(_msg(), task_type="fast")

    assert result.provider is Provider.GEMINI
    assert groq.calls == 2  # initial try + one retry, then fall back
    assert gemini.calls == 1


async def test_skips_unconfigured_providers() -> None:
    # Only Gemini is configured; groq/ollama absent from the chain.
    gemini = FakeClient(Provider.GEMINI)
    router = ProviderRouter(_settings(), clients={Provider.GEMINI: gemini})

    result = await router.complete(_msg(), task_type="fast")

    assert result.provider is Provider.GEMINI


async def test_auth_error_disables_provider_for_process() -> None:
    groq = FakeClient(Provider.GROQ, behaviors=[ProviderAuthError("bad key")])
    gemini = FakeClient(Provider.GEMINI)
    router = ProviderRouter(
        _settings(), clients={Provider.GROQ: groq, Provider.GEMINI: gemini}
    )

    first = await router.complete(_msg(), task_type="fast")
    second = await router.complete(_msg(), task_type="fast")

    assert first.provider is Provider.GEMINI
    assert second.provider is Provider.GEMINI
    # Groq was tried exactly once (first call); the second call skipped it entirely.
    assert groq.calls == 1


async def test_multimodal_exhausted_raises() -> None:
    gemini = FakeClient(Provider.GEMINI, behaviors=[ProviderRateLimitError("429")] * 5)
    router = ProviderRouter(
        _settings(),
        clients={Provider.GEMINI: gemini},
        sleep=SleepRecorder(),
    )

    with pytest.raises(ProviderExhaustedError) as excinfo:
        await router.complete(_msg(), task_type="multimodal")

    assert Provider.GEMINI in excinfo.value.failures


async def test_image_input_forces_multimodal_chain() -> None:
    # A "fast" call carrying an image must not fall to text-only providers.
    groq = FakeClient(Provider.GROQ)
    router = ProviderRouter(_settings(), clients={Provider.GROQ: groq})
    messages = [
        ChatMessage(role="user", content=[ImagePart(data=b"\x89PNG", mime_type="image/png")])
    ]

    with pytest.raises(ProviderExhaustedError):
        await router.complete(messages, task_type="fast")
    assert groq.calls == 0  # never routed to a text-only provider


async def test_cacheable_calls_hit_cache() -> None:
    groq = FakeClient(Provider.GROQ)
    router = ProviderRouter(_settings(), clients={Provider.GROQ: groq})

    first = await router.complete(_msg(), task_type="fast", cacheable=True)
    second = await router.complete(_msg(), task_type="fast", cacheable=True)

    assert groq.calls == 1  # second served from cache
    assert first.cached is False
    assert second.cached is True
    assert router.cache.stats()["hits"] == 1


async def test_non_cacheable_calls_bypass_cache() -> None:
    groq = FakeClient(Provider.GROQ)
    router = ProviderRouter(_settings(), clients={Provider.GROQ: groq})

    await router.complete(_msg(), task_type="fast", cacheable=False)
    await router.complete(_msg(), task_type="fast", cacheable=False)

    assert groq.calls == 2


async def test_retry_after_is_honored_and_capped() -> None:
    # First attempt asks for a 100s wait; the router caps total wait at 10s.
    groq = FakeClient(
        Provider.GROQ,
        behaviors=[ProviderRateLimitError("429", retry_after=100.0), None],
    )
    sleeper = SleepRecorder()
    router = ProviderRouter(
        _settings(),
        clients={Provider.GROQ: groq},
        sleep=sleeper,
    )

    result = await router.complete(_msg(), task_type="fast")

    assert result.provider is Provider.GROQ
    assert sleeper.calls == [10.0]  # honoured retry_after, clamped to the 10s budget


async def test_unavailable_provider_falls_back() -> None:
    groq = FakeClient(Provider.GROQ, behaviors=[ProviderUnavailableError("down")] * 5)
    ollama = FakeClient(Provider.OLLAMA)
    router = ProviderRouter(
        _settings(),
        clients={Provider.GROQ: groq, Provider.OLLAMA: ollama},
        sleep=SleepRecorder(),
    )

    result = await router.complete(_msg(), task_type="fast")
    assert result.provider is Provider.OLLAMA


@pytest.mark.integration
async def test_real_groq_smoke() -> None:
    """Manual smoke test: a single real Groq call. Skipped unless GROQ_API_KEY is set."""
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY not set; integration test skipped")
    router = ProviderRouter(Settings())
    result = await router.complete(
        [ChatMessage(role="user", content="Reply with the single word: ok")],
        task_type="fast",
        max_tokens=8,
    )
    assert result.text

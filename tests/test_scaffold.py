"""Phase 0 scaffold tests: config loads, every module imports, /health returns 200."""

from __future__ import annotations

import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from teacher_copilot.config import Env, Settings

# Every module in the package must import cleanly (stubs included).
ALL_MODULES = [
    "teacher_copilot",
    "teacher_copilot.config",
    "teacher_copilot.providers.router",
    "teacher_copilot.providers.groq_client",
    "teacher_copilot.providers.gemini_client",
    "teacher_copilot.providers.ollama_client",
    "teacher_copilot.providers.cache",
    "teacher_copilot.orchestrator.graph",
    "teacher_copilot.orchestrator.state",
    "teacher_copilot.orchestrator.intent",
    "teacher_copilot.agents.base",
    "teacher_copilot.agents.grading",
    "teacher_copilot.agents.lesson_plan",
    "teacher_copilot.agents.wellbeing",
    "teacher_copilot.agents.career",
    "teacher_copilot.memory.vector_store",
    "teacher_copilot.memory.embeddings",
    "teacher_copilot.memory.profile",
    "teacher_copilot.api.main",
    "teacher_copilot.observability.tracing",
]


@pytest.mark.parametrize("module_name", ALL_MODULES)
def test_module_imports(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None


def test_settings_instantiate_with_defaults() -> None:
    # Constructed without a .env / real keys: must boot with sane defaults.
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.env in (Env.DEV, Env.PROD)
    assert settings.qdrant_url.startswith("http")
    assert settings.ollama_url.startswith("http")
    assert settings.groq_configured is False
    assert settings.gemini_configured is False


def test_settings_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("ENV", "prod")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.env is Env.PROD
    assert settings.groq_configured is True


async def test_health_returns_200() -> None:
    from teacher_copilot.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

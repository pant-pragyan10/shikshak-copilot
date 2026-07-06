"""Settings tests: tiered model defaults and legacy env-var mapping."""

from __future__ import annotations

import pytest

from teacher_copilot.config import Settings


def _settings(**env: str) -> Settings:
    # Ignore any real .env; drive purely from the provided vars.
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_model_tier_defaults() -> None:
    settings = _settings()
    assert settings.groq_fast_model == "openai/gpt-oss-20b"
    assert settings.groq_smart_model == "openai/gpt-oss-120b"
    assert settings.gemini_bulk_model == "gemini-3.1-flash-lite"
    assert settings.gemini_smart_model == "gemini-3.5-flash"


def test_legacy_groq_model_maps_to_smart_tier_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_MODEL", "legacy-groq")
    with pytest.warns(DeprecationWarning, match="GROQ_MODEL is deprecated"):
        settings = _settings()
    assert settings.groq_smart_model == "legacy-groq"
    # The fast tier keeps its default — only the smart tier is remapped.
    assert settings.groq_fast_model == "openai/gpt-oss-20b"


def test_legacy_gemini_model_maps_to_smart_tier_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "legacy-gemini")
    with pytest.warns(DeprecationWarning, match="GEMINI_MODEL is deprecated"):
        settings = _settings()
    assert settings.gemini_smart_model == "legacy-gemini"
    assert settings.gemini_bulk_model == "gemini-3.1-flash-lite"


def test_no_warning_without_legacy_vars(recwarn: pytest.WarningsRecorder) -> None:
    _settings()
    assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning)]

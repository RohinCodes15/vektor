import pytest
from pydantic import ValidationError

from app.analysis.provider import AnthropicProvider
from app.config import Settings
from app.main import build_analysis_provider


def test_ai_analysis_is_off_by_default() -> None:
    settings = Settings(_env_file=None)
    assert (settings.ai_provider, settings.ai_api_key) == ("none", None)
    assert build_analysis_provider(settings) is None


def test_the_anthropic_provider_uses_the_configured_model_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEKTOR_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("VEKTOR_AI_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("VEKTOR_AI_API_KEY", "sk-ant-test-secret")
    settings = Settings(_env_file=None)
    provider = build_analysis_provider(settings)
    assert isinstance(provider, AnthropicProvider)
    assert (provider.name, provider.model) == ("anthropic", "claude-sonnet-5-5")
    assert "sk-ant-test-secret" not in repr(settings) and "sk-ant-test-secret" not in str(settings.model_dump())


def test_ai_settings_are_validated() -> None:
    for bad in [{"ai_provider": "openai"}, {"ai_timeout_seconds": 0}, {"ai_timeout_seconds": 601}, {"ai_model": ""}]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **bad)

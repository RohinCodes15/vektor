import pytest
from pydantic import ValidationError

from app.analysis.provider import AnthropicProvider
from app.config import Settings
from app.main import build_analysis_provider


def test_ai_analysis_is_off_by_default() -> None:
    settings = Settings(_env_file=None)
    assert (settings.ai_provider, settings.ai_api_key) == ("none", None)
    assert build_analysis_provider(settings) is None

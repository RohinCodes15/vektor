from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from app.analysis.errors import AnalysisUnavailable, InvalidAnalysis
from app.analysis.provider import MAX_OUTPUT_TOKENS, MAX_RETRIES, AnthropicProvider
from app.contracts import AnalysisInterpretation
from tests.analysis_support import interpretation

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
SECRET_BODY = {"error": {"message": "internal provider detail sk-ant-leaked"}}


def response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=REQUEST)


class FakeMessages:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeClientFactory:
    """Stands in for anthropic.Anthropic: records constructor options; no network."""

    def __init__(self, outcome: Any) -> None:
        self.messages = FakeMessages(outcome)
        self.options: dict[str, Any] = {}

    def __call__(self, **options: Any) -> SimpleNamespace:
        self.options = options
        return SimpleNamespace(messages=self.messages)


def reply(parsed: object = None, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=interpretation() if parsed is None else parsed)


def provider(factory: Any, api_key: str | None = "sk-test") -> AnthropicProvider:
    return AnthropicProvider("claude-opus-5-5", api_key, 30, client_factory=factory)


def test_a_structured_reply_is_returned_and_the_request_is_minimal() -> None:
    factory = FakeClientFactory(reply())
    assert provider(factory).interpret("system rules", '{"facts":[]}') == interpretation()
    assert factory.options == {"api_key": "sk-test", "timeout": 30, "max_retries": MAX_RETRIES}
    assert factory.messages.kwargs == {
        "model": "claude-opus-5-5", "max_tokens": MAX_OUTPUT_TOKENS, "system": "system rules",
        "messages": [{"role": "user", "content": '{"facts":[]}'}], "output_format": AnalysisInterpretation,
    }


def test_without_a_configured_key_the_sdk_resolves_its_own_credentials() -> None:
    factory = FakeClientFactory(reply())
    provider(factory, api_key=None).interpret("s", "p")
    assert "api_key" not in factory.options


def test_missing_credentials_are_unavailable() -> None:
    def no_credentials(**_: Any) -> None:
        raise anthropic.CredentialsError("no credentials")

    with pytest.raises(AnalysisUnavailable, match="no provider credentials"):
        provider(no_credentials, api_key=None).interpret("s", "p")

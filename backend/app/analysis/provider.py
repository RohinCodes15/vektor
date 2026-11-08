"""AI providers for backtest analysis. Any object with `name`, `model` and `interpret()` can serve as one.

AnthropicProvider calls Claude through the official SDK with structured output, so the reply must match the
AnalysisInterpretation contract. Every failure becomes AnalysisUnavailable (503: timeout, rate limit, network,
overload, missing or rejected credentials) or InvalidAnalysis (502: request rejected, refusal, truncated or malformed
reply). Provider error bodies and the API key are never logged or returned.
"""

import logging
from collections.abc import Callable
from typing import Protocol

import anthropic
from pydantic import ValidationError

from app.analysis.errors import AnalysisUnavailable, InvalidAnalysis
from app.contracts import AnalysisInterpretation, AnalysisProviderName

logger = logging.getLogger("vektor.analysis")

# Room for adaptive thinking plus the structured reply; a non-streaming request stays well under SDK timeouts.
MAX_OUTPUT_TOKENS = 16000
# One retry for transient failures (the SDK retries 408/409/429/5xx and connection errors), so a request takes at most
# two timeouts.
MAX_RETRIES = 1


class AnalysisProvider(Protocol):
    name: AnalysisProviderName
    model: str

    def interpret(self, system: str, payload: str) -> AnalysisInterpretation:
        """Interpret the measured facts in `payload`. Raises AnalysisUnavailable or InvalidAnalysis."""
        ...


class AnthropicProvider:
    name: AnalysisProviderName = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        client_factory: Callable[..., anthropic.Anthropic] = anthropic.Anthropic,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory

    def interpret(self, system: str, payload: str) -> AnalysisInterpretation:
        try:
            response = self._client().messages.parse(
                model=self.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": payload}],
                output_format=AnalysisInterpretation,
            )
        except anthropic.APIResponseValidationError:
            logger.warning("AI provider response failed SDK validation", extra={"model": self.model})
            raise InvalidAnalysis("The AI provider returned a malformed analysis.") from None
        except anthropic.APIError as error:
            raise _provider_error(error) from None
        except anthropic.AnthropicError as error:
            logger.warning("AI provider client failed", extra={"model": self.model, "error": type(error).__name__})
            raise AnalysisUnavailable("The AI provider could not be used. Try again later.") from None
        except (ValidationError, ValueError):
            logger.warning("AI provider reply did not match the analysis contract", extra={"model": self.model})
            raise InvalidAnalysis("The AI provider returned a malformed analysis.") from None
        return _interpretation(response.stop_reason, response.parsed_output, self.model)

    def _client(self) -> anthropic.Anthropic:
        """A client per request; with no key configured the SDK resolves its own credentials (ANTHROPIC_API_KEY)."""
        options = {"timeout": self._timeout_seconds, "max_retries": MAX_RETRIES}
        try:
            if self._api_key is None:
                return self._client_factory(**options)
            return self._client_factory(api_key=self._api_key, **options)
        except anthropic.AnthropicError:
            logger.warning("AI provider credentials are missing", extra={"model": self.model})
            raise AnalysisUnavailable("AI analysis is enabled but no provider credentials were found.") from None


def _interpretation(stop_reason: str | None, parsed: object, model: str) -> AnalysisInterpretation:
    if stop_reason == "refusal":
        logger.warning("AI provider declined the analysis", extra={"model": model})
        raise InvalidAnalysis("The AI provider declined to analyze this backtest.")
    if stop_reason == "max_tokens":
        logger.warning("AI provider reply was truncated", extra={"model": model})
        raise InvalidAnalysis("The AI provider returned an incomplete analysis.")
    if not isinstance(parsed, AnalysisInterpretation):
        logger.warning("AI provider reply had no structured analysis", extra={"model": model})
        raise InvalidAnalysis("The AI provider returned a malformed analysis.")
    return parsed


def _provider_error(error: anthropic.APIError) -> AnalysisUnavailable | InvalidAnalysis:
    """Map an SDK error to a safe client message. Most specific first: timeouts are connection errors."""
    status = getattr(error, "status_code", None)
    logger.warning("AI provider request failed", extra={"error": type(error).__name__, "http_status": status})
    if isinstance(error, anthropic.APITimeoutError):
        return AnalysisUnavailable("The AI provider timed out. Try again later.")
    if isinstance(error, anthropic.APIConnectionError):
        return AnalysisUnavailable("The AI provider could not be reached. Try again later.")
    if isinstance(error, anthropic.RateLimitError):
        return AnalysisUnavailable("The AI provider is rate limiting requests. Try again later.")
    if isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return AnalysisUnavailable("The AI provider rejected the configured credentials.")
    if isinstance(status, int) and status >= 500:
        return AnalysisUnavailable("The AI provider is overloaded or failing. Try again later.")
    return InvalidAnalysis("The AI provider rejected the analysis request.")

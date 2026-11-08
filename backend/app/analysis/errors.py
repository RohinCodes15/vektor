"""AI analysis failures. Messages are safe to show to API clients; provider details are only logged."""


class AnalysisError(Exception):
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AnalysisUnavailable(AnalysisError):
    """The AI provider timed out, rate-limited the request, could not be reached, or has no usable credentials."""

    status_code = 503


class InvalidAnalysis(AnalysisError):
    """The AI provider rejected the request, declined it, or returned an analysis that fails validation."""

    status_code = 502

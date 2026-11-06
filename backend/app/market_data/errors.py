"""Market data failures. Messages are safe to show to API clients; provider details are only logged."""


class MarketDataError(Exception):
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MarketDataNotFound(MarketDataError):
    """The provider has no bars for the symbol and range (unknown symbol, or no trading days)."""

    status_code = 404


class InvalidMarketData(MarketDataError):
    """The provider returned data that fails validation; it is rejected, never repaired or filled."""

    status_code = 502


class MarketDataUnavailable(MarketDataError):
    """The provider could not be reached, timed out, or rate-limited the request."""

    status_code = 503

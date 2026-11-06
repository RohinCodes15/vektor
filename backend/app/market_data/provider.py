"""Historical price providers. Yahoo Finance via yfinance: free, no API key, read-only."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import yfinance as yf
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError, YFTzMissingError

from app.contracts import MarketDataSource, PriceBar
from app.market_data.errors import MarketDataNotFound, MarketDataUnavailable
from app.market_data.normalize import normalize_daily_frame

logger = logging.getLogger("vektor.market_data")

REQUEST_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ProviderHistory:
    currency: str | None
    bars: tuple[PriceBar, ...]


class HistoryProvider(Protocol):
    source: MarketDataSource

    def fetch_daily_history(self, symbol: str, start: date, end: date) -> ProviderHistory:
        """Validated daily bars dated within [start, end] (inclusive); may be empty."""
        ...


class YFinanceProvider:
    source: MarketDataSource = "yahoo_finance"

    def __init__(self, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds
        # Surface Yahoo failures as exceptions instead of logged errors and empty frames.
        yf.config.debug.hide_exceptions = False

    def fetch_daily_history(self, symbol: str, start: date, end: date) -> ProviderHistory:
        ticker = yf.Ticker(symbol)
        try:
            frame = ticker.history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),  # yfinance's end is exclusive
                interval="1d",
                auto_adjust=False,  # keep reported OHLC and the separate Adj Close
                actions=False,
                timeout=self._timeout_seconds,
            )
        except (YFPricesMissingError, YFTzMissingError):
            logger.info("provider has no history", extra={"symbol": symbol, "start": start, "end": end})
            raise MarketDataNotFound.for_range(symbol, start, end) from None
        except YFRateLimitError:
            logger.warning("provider rate limited", extra={"symbol": symbol})
            raise MarketDataUnavailable("Yahoo Finance is rate limiting requests. Try again later.") from None
        except Exception:
            logger.warning("provider request failed", extra={"symbol": symbol}, exc_info=True)
            raise MarketDataUnavailable("Yahoo Finance could not be reached. Try again later.") from None
        return ProviderHistory(currency=_currency(ticker), bars=normalize_daily_frame(frame, start, end))


def _currency(ticker: yf.Ticker) -> str | None:
    """Currency from the metadata of the history request just made (no extra request)."""
    try:
        currency = ticker.get_history_metadata().get("currency")
    except Exception:
        logger.warning("provider metadata unavailable", exc_info=True)
        return None
    return currency.strip() if isinstance(currency, str) and currency.strip() else None  # as reported, e.g. "GBp"

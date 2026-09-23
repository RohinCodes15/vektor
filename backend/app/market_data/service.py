"""Read-only historical prices: serve from the local cache when fresh, otherwise fetch from the provider."""

import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.contracts import MarketHistoryQuery, MarketHistoryResponse
from app.market_data.cache import HistoryCache
from app.market_data.errors import MarketDataNotFound
from app.market_data.provider import HistoryProvider

logger = logging.getLogger("vektor.market_data")

# Exchanges ahead of UTC can have a bar dated one day after today's UTC date.
PROVIDER_END_LEEWAY = timedelta(days=1)


def utc_now() -> datetime:
    return datetime.now(UTC)


class MarketDataService:
    def __init__(
        self,
        provider: HistoryProvider,
        cache: HistoryCache,
        cache_ttl: timedelta,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._cache_ttl = cache_ttl
        self._clock = clock

    def get_history(self, query: MarketHistoryQuery) -> MarketHistoryResponse:
        """Daily bars for the query, or MarketDataNotFound when there are none. Never fabricates bars."""
        now = self._clock()
        history = self._load_cached(query, fresh_after=now - self._cache_ttl)
        if history is None:
            history = self._fetch(query, now)
            # Only completed days are cached; a range reaching today may still change.
            if history.bars and query.end < now.date():
                self._store(history, expire_before=now - self._cache_ttl)
        if not history.bars:
            raise MarketDataNotFound.for_range(query.symbol, query.start, query.end)
        logger.info(
            "market history served",
            extra={"symbol": query.symbol, "start": query.start, "end": query.end,
                   "cached": history.cached, "bars": len(history.bars)},
        )
        return history

    def _fetch(self, query: MarketHistoryQuery, now: datetime) -> MarketHistoryResponse:
        provider_end = min(query.end, now.date() + PROVIDER_END_LEEWAY)
        fetched = self._provider.fetch_daily_history(query.symbol, query.start, provider_end)
        return MarketHistoryResponse(
            symbol=query.symbol,
            interval=query.interval,
            start=query.start,
            end=query.end,
            currency=fetched.currency,
            source=self._provider.source,
            cached=False,
            fetched_at=now,
            bars=list(fetched.bars),
        )

    def _load_cached(self, query: MarketHistoryQuery, fresh_after: datetime) -> MarketHistoryResponse | None:
        try:
            return self._cache.load(query, self._provider.source, fresh_after)
        except (sqlite3.Error, OSError, ValueError):  # ValueError includes Pydantic ValidationError
            logger.warning("market data cache read failed; using provider", exc_info=True)
            return None

    def _store(self, history: MarketHistoryResponse, expire_before: datetime) -> None:
        try:
            self._cache.store(history, expire_before)
        except (sqlite3.Error, OSError):
            logger.warning("market data cache write failed; response not cached", exc_info=True)

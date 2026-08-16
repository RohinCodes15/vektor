"""Read-only historical prices: serve from the local cache when fresh, otherwise fetch from the provider.

Provider fetches are bounded: at most `max_concurrent_fetches` run at once, and a request waits at most
FETCH_WAIT_SECONDS for its turn before it fails with 503 instead of hanging. Concurrent requests for the same
symbol and range wait for one fetch and then read its result from the cache, so a burst of identical requests makes
one provider call, not many.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import UTC, date, datetime, timedelta

from app.contracts import MarketHistoryQuery, MarketHistoryResponse
from app.market_data.cache import HistoryCache
from app.market_data.errors import MarketDataError, MarketDataNotFound, MarketDataUnavailable
from app.market_data.provider import HistoryProvider

logger = logging.getLogger("vektor.market_data")

# Exchanges ahead of UTC can have a bar dated one day after today's UTC date.
PROVIDER_END_LEEWAY = timedelta(days=1)
DEFAULT_MAX_CONCURRENT_FETCHES = 4
# Longer than a provider fetch with its retry (about 2 x 10 s), shorter than typical proxy and browser timeouts.
FETCH_WAIT_SECONDS = 30.0
BUSY = "Market data requests are busy. Try again shortly."
RangeKey = tuple[str, date, date]  # (symbol, start, end)


def utc_now() -> datetime:
    return datetime.now(UTC)


class MarketDataService:
    def __init__(
        self,
        provider: HistoryProvider,
        cache: HistoryCache,
        cache_ttl: timedelta,
        clock: Callable[[], datetime] = utc_now,
        max_concurrent_fetches: int = DEFAULT_MAX_CONCURRENT_FETCHES,
        fetch_wait_seconds: float = FETCH_WAIT_SECONDS,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._cache_ttl = cache_ttl
        self._clock = clock
        self._fetch_slots = threading.BoundedSemaphore(max_concurrent_fetches)
        # One lock per (symbol, start, end) being fetched, with the number of requests using it; removed when unused.
        self._range_locks: dict[RangeKey, tuple[threading.Lock, int]] = {}
        self._range_locks_guard = threading.Lock()
        self._fetch_wait_seconds = fetch_wait_seconds

    def get_history(self, query: MarketHistoryQuery) -> MarketHistoryResponse:
        """Daily bars for the query, or MarketDataNotFound when there are none. Never fabricates bars."""
        now = self._clock()
        history = self._load_cached(query, fresh_after=now - self._cache_ttl)
        return self._served(query, history if history is not None else self._fetch_once(query, now))

    def get_histories(self, queries: Sequence[MarketHistoryQuery]) -> list[MarketHistoryResponse | MarketDataError]:
        """get_history for each query, in order, with each failure returned in its query's place instead of raised.

        Cached queries are read one after another (parsing is CPU-bound, so threads would only contend); uncached
        ones are fetched concurrently, still within the bounded fetch slots, so N cold symbols cost about one
        provider round trip per slot rather than N.
        """
        now = self._clock()
        cached = [self._load_cached(query, fresh_after=now - self._cache_ttl) for query in queries]
        misses = [i for i, history in enumerate(cached) if history is None]
        fetched: dict[int, MarketHistoryResponse | MarketDataError] = {}
        if len(misses) == 1:
            fetched[misses[0]] = _outcome(lambda: self._fetch_once(queries[misses[0]], now))
        elif misses:
            with ThreadPoolExecutor(max_workers=len(misses), thread_name_prefix="vektor-fetch") as pool:
                futures = {i: pool.submit(self._fetch_once, queries[i], now) for i in misses}
                fetched = {i: _outcome(future.result) for i, future in futures.items()}
        results: list[MarketHistoryResponse | MarketDataError] = []
        for i, query in enumerate(queries):
            history = cached[i] if cached[i] is not None else fetched[i]
            results.append(history if isinstance(history, MarketDataError) else _outcome(
                lambda q=query, h=history: self._served(q, h)
            ))
        return results

    def _served(self, query: MarketHistoryQuery, history: MarketHistoryResponse) -> MarketHistoryResponse:
        if not history.bars:
            raise MarketDataNotFound.for_range(query.symbol, query.start, query.end)
        logger.info(
            "market history served",
            extra={"symbol": query.symbol, "start": query.start, "end": query.end,
                   "cached": history.cached, "bars": len(history.bars)},
        )
        return history

    def _fetch_once(self, query: MarketHistoryQuery, now: datetime) -> MarketHistoryResponse:
        fresh_after = now - self._cache_ttl
        with self._fetch_turn(query):
            # A concurrent request for the same range may have fetched and cached it while this one waited.
            cached = self._load_cached(query, fresh_after)
            if cached is not None:
                return cached
            history = self._fetch(query, now)
            # Only completed days are cached; a range reaching today may still change.
            if history.bars and query.end < now.date():
                self._store(history, expire_before=fresh_after)
        return history

    @contextmanager
    def _fetch_turn(self, query: MarketHistoryQuery) -> Iterator[None]:
        """Hold this range's lock and one of the bounded fetch slots, or fail with 503 after waiting too long."""
        deadline = time.monotonic() + self._fetch_wait_seconds  # one budget for both waits
        with ExitStack() as held:
            range_lock = held.enter_context(self._range_lock((query.symbol, query.start, query.end)))
            for gate in (range_lock, self._fetch_slots):
                if not gate.acquire(timeout=max(0.0, deadline - time.monotonic())):
                    logger.warning("market data fetch timed out waiting for a slot", extra={"symbol": query.symbol})
                    raise MarketDataUnavailable(BUSY)
                held.callback(gate.release)
            yield

    @contextmanager
    def _range_lock(self, key: RangeKey) -> Iterator[threading.Lock]:
        """The lock shared by every request currently fetching `key`; unrelated ranges never wait on each other."""
        with self._range_locks_guard:
            lock, users = self._range_locks.get(key, (threading.Lock(), 0))
            self._range_locks[key] = (lock, users + 1)
        try:
            yield lock
        finally:
            with self._range_locks_guard:
                lock, users = self._range_locks[key]
                if users == 1:
                    del self._range_locks[key]
                else:
                    self._range_locks[key] = (lock, users - 1)

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


def _outcome(call: Callable[[], MarketHistoryResponse]) -> MarketHistoryResponse | MarketDataError:
    try:
        return call()
    except MarketDataError as error:
        return error

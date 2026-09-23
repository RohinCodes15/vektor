import logging
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts import MarketHistoryQuery
from app.market_data.cache import HistoryCache
from app.market_data.errors import InvalidMarketData, MarketDataNotFound, MarketDataUnavailable
from app.market_data.service import MarketDataService
from tests.fakes import FakeProvider, make_bar

NOW = datetime(2024, 3, 1, 15, 30, tzinfo=UTC)
TTL = timedelta(hours=24)


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def query(start: str = "2024-01-01", end: str = "2024-01-31", symbol: str = "AAPL") -> MarketHistoryQuery:
    return MarketHistoryQuery(symbol=symbol, start=start, end=end)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(provider: FakeProvider, tmp_path: Path, clock: Clock) -> MarketDataService:
    return MarketDataService(provider, HistoryCache(tmp_path / "cache.sqlite3"), TTL, clock=clock)


def test_fetches_from_the_provider_on_a_cache_miss(service: MarketDataService, provider: FakeProvider) -> None:
    res = service.get_history(query())
    assert provider.calls == [("AAPL", date(2024, 1, 1), date(2024, 1, 31))]
    assert res.cached is False and res.fetched_at == NOW
    assert (res.symbol, res.interval, res.start, res.end, res.currency, res.source) == (
        "AAPL",
        "1d",
        date(2024, 1, 1),
        date(2024, 1, 31),
        "USD",
        "yahoo_finance",
    )
    assert [bar.date for bar in res.bars] == [date(2024, 1, 2), date(2024, 1, 3)]


def test_serves_repeat_and_covered_requests_from_the_cache(
    service: MarketDataService, provider: FakeProvider, clock: Clock
) -> None:
    first = service.get_history(query())
    clock.now = NOW + timedelta(hours=23)
    again = service.get_history(query())
    narrower = service.get_history(query("2024-01-03", "2024-01-10"))
    assert len(provider.calls) == 1
    assert again == first.model_copy(update={"cached": True})
    assert again.fetched_at == NOW
    assert [bar.date for bar in narrower.bars] == [date(2024, 1, 3)]


def test_refetches_after_the_cache_ttl(service: MarketDataService, provider: FakeProvider, clock: Clock) -> None:
    service.get_history(query())
    clock.now = NOW + TTL + timedelta(seconds=1)
    res = service.get_history(query())
    assert len(provider.calls) == 2 and res.cached is False and res.fetched_at == clock.now


def test_refetches_wider_ranges(service: MarketDataService, provider: FakeProvider) -> None:
    service.get_history(query("2024-01-02", "2024-01-02"))
    service.get_history(query("2024-01-01", "2024-01-31"))
    assert len(provider.calls) == 2


@pytest.mark.parametrize("end", ["2024-03-01", "2024-03-02", "2030-01-01"])
def test_does_not_cache_ranges_reaching_today_or_later(
    service: MarketDataService, provider: FakeProvider, end: str
) -> None:
    provider.bars = [make_bar("2024-02-29"), make_bar("2024-03-01")]
    first = service.get_history(query("2024-02-01", end))
    service.get_history(query("2024-02-01", end))
    assert len(provider.calls) == 2
    assert first.end == date.fromisoformat(end)


def test_caches_ranges_ending_yesterday(service: MarketDataService, provider: FakeProvider) -> None:
    provider.bars = [make_bar("2024-02-29")]
    service.get_history(query("2024-02-01", "2024-02-29"))
    service.get_history(query("2024-02-01", "2024-02-29"))
    assert len(provider.calls) == 1


def test_limits_the_provider_request_to_one_day_past_today(service: MarketDataService, provider: FakeProvider) -> None:
    provider.bars = [make_bar("2024-02-29")]
    res = service.get_history(query("2024-02-01", "2099-12-31"))
    assert provider.calls == [("AAPL", date(2024, 2, 1), date(2024, 3, 2))]
    assert res.end == date(2099, 12, 31)


def test_no_bars_is_not_found_and_not_cached(service: MarketDataService, provider: FakeProvider) -> None:
    provider.bars = []
    for _ in range(2):
        with pytest.raises(
            MarketDataNotFound, match="No daily price history found for AAPL between 2024-01-01 and 2024-01-31"
        ):
            service.get_history(query())
    assert len(provider.calls) == 2


def test_cached_range_without_trading_days_is_not_found(service: MarketDataService, provider: FakeProvider) -> None:
    service.get_history(query())
    with pytest.raises(MarketDataNotFound):
        service.get_history(query("2024-01-06", "2024-01-07"))
    assert len(provider.calls) == 1


@pytest.mark.parametrize("error", [MarketDataUnavailable("down"), InvalidMarketData("bad"), MarketDataNotFound("none")])
def test_provider_errors_propagate_and_nothing_is_cached(
    service: MarketDataService, provider: FakeProvider, error: Exception
) -> None:
    provider.error = error
    with pytest.raises(type(error)):
        service.get_history(query())
    provider.error = None
    assert service.get_history(query()).cached is False


def test_unreadable_cache_falls_back_to_the_provider(
    provider: FakeProvider, tmp_path: Path, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "cache.sqlite3"
    path.write_bytes(b"not a database" * 100)
    service = MarketDataService(provider, HistoryCache(path), TTL, clock=clock)
    with caplog.at_level(logging.WARNING, logger="vektor.market_data"):
        res = service.get_history(query())
    assert res.cached is False and len(res.bars) == 2
    assert "cache read failed" in caplog.text and "cache write failed" in caplog.text


def test_corrupt_cached_bars_fall_back_to_the_provider(
    service: MarketDataService, provider: FakeProvider, tmp_path: Path
) -> None:
    service.get_history(query())
    with sqlite3.connect(tmp_path / "cache.sqlite3") as conn:
        conn.execute("UPDATE history_bars SET high = -1")
    res = service.get_history(query())
    assert res.cached is False and len(provider.calls) == 2


def test_failed_cache_write_still_returns_data(
    provider: FakeProvider, clock: Clock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = HistoryCache(tmp_path / "cache.sqlite3")

    def fail(*_: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(cache, "store", fail)
    res = MarketDataService(provider, cache, TTL, clock=clock).get_history(query())
    assert res.cached is False and len(res.bars) == 2


def test_logs_each_served_request(service: MarketDataService, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="vektor.market_data"):
        service.get_history(query())
    (record,) = (r for r in caplog.records if r.getMessage() == "market history served")
    assert (record.symbol, record.cached, record.bars) == ("AAPL", False, 2)

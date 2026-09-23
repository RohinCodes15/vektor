import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts import MarketHistoryQuery, MarketHistoryResponse, PriceBar
from app.market_data.cache import HistoryCache

FETCHED = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
LONG_AGO = FETCHED - timedelta(days=365)


def bar(day: str, close: float = 11.0) -> PriceBar:
    return PriceBar(
        date=day, open=10, high=max(12, close), low=9.5, close=close, adjusted_close=close - 0.2, volume=1000
    )


def response(
    start: str = "2024-01-01",
    end: str = "2024-01-31",
    fetched_at: datetime = FETCHED,
    symbol: str = "AAPL",
    bars: list[PriceBar] | None = None,
    currency: str | None = "USD",
) -> MarketHistoryResponse:
    return MarketHistoryResponse(
        symbol=symbol,
        interval="1d",
        start=start,
        end=end,
        currency=currency,
        source="yahoo_finance",
        cached=False,
        fetched_at=fetched_at,
        bars=bars if bars is not None else [bar("2024-01-02"), bar("2024-01-16", 12.0), bar("2024-01-31", 11.5)],
    )


def query(start: str = "2024-01-01", end: str = "2024-01-31", symbol: str = "AAPL") -> MarketHistoryQuery:
    return MarketHistoryQuery(symbol=symbol, start=start, end=end)


@pytest.fixture
def cache(tmp_path: Path) -> HistoryCache:
    return HistoryCache(tmp_path / "nested" / "cache.sqlite3")


def count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_creates_the_database_lazily(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "cache.sqlite3"
    cache = HistoryCache(path)
    assert not path.exists()
    assert cache.load(query(), "yahoo_finance", LONG_AGO) is None
    assert path.exists()


def test_round_trips_a_provider_response(cache: HistoryCache) -> None:
    original = response()
    cache.store(original, expire_before=LONG_AGO)
    loaded = cache.load(query(), "yahoo_finance", LONG_AGO)
    assert loaded == original.model_copy(update={"cached": True})
    assert loaded.fetched_at == FETCHED


def test_serves_a_covered_sub_range_trimmed_to_the_query(cache: HistoryCache) -> None:
    cache.store(response(), expire_before=LONG_AGO)
    loaded = cache.load(query("2024-01-10", "2024-01-20"), "yahoo_finance", LONG_AGO)
    assert loaded is not None
    assert (loaded.start, loaded.end) == (date(2024, 1, 10), date(2024, 1, 20))
    assert [b.date for b in loaded.bars] == [date(2024, 1, 16)]


def test_a_covered_range_without_trading_days_loads_empty(cache: HistoryCache) -> None:
    cache.store(response(), expire_before=LONG_AGO)
    loaded = cache.load(query("2024-01-06", "2024-01-07"), "yahoo_finance", LONG_AGO)
    assert loaded is not None and loaded.bars == []


@pytest.mark.parametrize(
    ("start", "end"), [("2023-12-31", "2024-01-31"), ("2024-01-01", "2024-02-01"), ("2024-02-01", "2024-02-28")]
)
def test_misses_ranges_not_fully_covered_by_one_entry(cache: HistoryCache, start: str, end: str) -> None:
    cache.store(response(), expire_before=LONG_AGO)
    assert cache.load(query(start, end), "yahoo_finance", LONG_AGO) is None


def test_never_stitches_adjacent_entries(cache: HistoryCache) -> None:
    cache.store(response("2024-01-01", "2024-01-15", bars=[bar("2024-01-02")]), expire_before=LONG_AGO)
    cache.store(response("2024-01-16", "2024-01-31", bars=[bar("2024-01-16")]), expire_before=LONG_AGO)
    assert cache.load(query("2024-01-10", "2024-01-20"), "yahoo_finance", LONG_AGO) is None


def test_misses_other_symbols_and_sources(cache: HistoryCache) -> None:
    cache.store(response(), expire_before=LONG_AGO)
    assert cache.load(query(symbol="MSFT"), "yahoo_finance", LONG_AGO) is None
    assert cache.load(query(), "other_source", LONG_AGO) is None


def test_ignores_entries_fetched_before_the_freshness_cutoff(cache: HistoryCache) -> None:
    cache.store(response(), expire_before=LONG_AGO)
    assert cache.load(query(), "yahoo_finance", FETCHED) is not None
    assert cache.load(query(), "yahoo_finance", FETCHED + timedelta(microseconds=1)) is None


def test_prefers_the_newest_covering_entry(cache: HistoryCache) -> None:
    cache.store(response("2023-12-01", "2024-02-28", bars=[bar("2024-01-02", 11.0)]), expire_before=LONG_AGO)
    newer = FETCHED + timedelta(hours=1)
    cache.store(
        response("2024-01-01", "2024-01-31", fetched_at=newer, bars=[bar("2024-01-02", 99.0)]), expire_before=LONG_AGO
    )
    loaded = cache.load(query(), "yahoo_finance", LONG_AGO)
    assert loaded is not None and loaded.fetched_at == newer and loaded.bars[0].close == 99.0


def test_store_drops_superseded_and_expired_entries(cache: HistoryCache, tmp_path: Path) -> None:
    path = tmp_path / "nested" / "cache.sqlite3"
    cache.store(response("2024-01-10", "2024-01-20", bars=[bar("2024-01-16")]), expire_before=LONG_AGO)
    cache.store(response(symbol="MSFT", fetched_at=FETCHED - timedelta(days=2)), expire_before=LONG_AGO)
    cache.store(response("2024-01-01", "2024-01-31"), expire_before=FETCHED - timedelta(days=1))
    assert count(path, "history_fetches") == 1
    assert count(path, "history_bars") == 3
    assert cache.load(query(symbol="MSFT"), "yahoo_finance", LONG_AGO) is None


def test_keeps_overlapping_entries_it_does_not_contain(cache: HistoryCache) -> None:
    cache.store(response("2023-12-01", "2024-01-15", bars=[bar("2024-01-02")]), expire_before=LONG_AGO)
    cache.store(response("2024-01-01", "2024-01-31"), expire_before=LONG_AGO)
    assert cache.load(query("2023-12-01", "2024-01-15"), "yahoo_finance", LONG_AGO) is not None


def test_stores_unknown_currency_and_empty_entries(cache: HistoryCache) -> None:
    cache.store(response(currency=None, bars=[]), expire_before=LONG_AGO)
    loaded = cache.load(query(), "yahoo_finance", LONG_AGO)
    assert loaded is not None and loaded.currency is None and loaded.bars == []


def test_failed_store_leaves_no_partial_entry(
    cache: HistoryCache, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "nested" / "cache.sqlite3"
    cache.load(query(), "yahoo_finance", LONG_AGO)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TRIGGER fail BEFORE INSERT ON history_bars BEGIN SELECT RAISE(ABORT, 'disk full'); END")
    with pytest.raises(sqlite3.Error):
        cache.store(response(), expire_before=LONG_AGO)
    assert count(path, "history_fetches") == 0


def test_corrupt_files_raise_sqlite_errors(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    path.write_bytes(b"not a database" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        HistoryCache(path).load(query(), "yahoo_finance", LONG_AGO)

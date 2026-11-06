from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.contracts import MarketHistoryQuery, MarketHistoryResponse, PriceBar


def query(**overrides: object) -> MarketHistoryQuery:
    return MarketHistoryQuery(**{"symbol": "AAPL", "start": "2024-01-02", "end": "2024-01-31", **overrides})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("aapl", "AAPL"),
        ("  msft ", "MSFT"),
        ("brk-b", "BRK-B"),
        ("BRK.B", "BRK.B"),
        ("^gspc", "^GSPC"),
        ("eurusd=x", "EURUSD=X"),
        ("7203.T", "7203.T"),
        ("A" * 15, "A" * 15),
    ],
)
def test_query_normalizes_valid_symbols(raw: str, expected: str) -> None:
    assert query(symbol=raw).symbol == expected


@pytest.mark.parametrize("raw", ["", "   ", "A" * 16, "AA PL", "AAPL;DROP", "^", "-AAPL", "AAPL/", "AAPL^", "ÄAPL"])
def test_query_rejects_invalid_symbols(raw: str) -> None:
    with pytest.raises(ValidationError, match="symbol must be"):
        query(symbol=raw)


def test_query_parses_dates_and_defaults_to_daily_interval() -> None:
    q = query()
    assert (q.start, q.end, q.interval) == (date(2024, 1, 2), date(2024, 1, 31), "1d")


def test_query_accepts_a_single_day_range() -> None:
    assert query(start="2024-01-02", end="2024-01-02").start == date(2024, 1, 2)


def test_query_rejects_start_after_end() -> None:
    with pytest.raises(ValidationError, match="start must be on or before end"):
        query(start="2024-02-01", end="2024-01-31")


def test_query_rejects_future_start() -> None:
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    with pytest.raises(ValidationError, match="start cannot be in the future"):
        query(start=tomorrow, end=tomorrow + timedelta(days=5))


@pytest.mark.parametrize(
    "overrides", [{"interval": "1h"}, {"start": "2024-13-01"}, {"end": "yesterday"}, {"extra": "x"}]
)
def test_query_rejects_unsupported_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        query(**overrides)


def test_query_is_immutable() -> None:
    with pytest.raises(ValidationError):
        query().symbol = "MSFT"  # type: ignore[misc]


BAR = {
    "date": "2024-01-02",
    "open": 10.0,
    "high": 12.0,
    "low": 9.5,
    "close": 11.0,
    "adjusted_close": 10.8,
    "volume": 1000,
}


def test_price_bar_accepts_valid_ohlcv() -> None:
    bar = PriceBar(**BAR)
    assert bar.date == date(2024, 1, 2) and bar.volume == 1000


def test_price_bar_accepts_a_flat_bar() -> None:
    assert PriceBar(**{**BAR, "open": 5, "high": 5, "low": 5, "close": 5, "adjusted_close": 5, "volume": 0}).high == 5


@pytest.mark.parametrize(
    "overrides",
    [
        {"open": 0},
        {"close": -1},
        {"adjusted_close": 0},
        {"high": float("nan")},
        {"low": float("inf")},
        {"volume": -1},
        {"volume": 1.5},
        {"open": None},
        {"date": "2024-02-30"},
    ],
)
def test_price_bar_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PriceBar(**{**BAR, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [{"high": 9.0}, {"low": 11.5}, {"open": 12.5}, {"close": 9.0}, {"high": 9.4, "low": 9.5}],
)
def test_price_bar_rejects_inconsistent_ranges(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="low <= open, close <= high"):
        PriceBar(**{**BAR, **overrides})


def history(**overrides: object) -> MarketHistoryResponse:
    fields = {
        "symbol": "AAPL",
        "interval": "1d",
        "start": "2024-01-01",
        "end": "2024-01-05",
        "currency": "USD",
        "source": "yahoo_finance",
        "cached": False,
        "fetched_at": "2024-01-06T00:00:00Z",
        "bars": [{**BAR, "date": "2024-01-02"}, {**BAR, "date": "2024-01-03"}],
    }
    return MarketHistoryResponse(**{**fields, **overrides})


def test_history_response_accepts_ordered_bars_in_range() -> None:
    res = history()
    assert [bar.date for bar in res.bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert res.fetched_at == datetime(2024, 1, 6, tzinfo=UTC)


def test_history_response_allows_unknown_currency() -> None:
    assert history(currency=None).currency is None


@pytest.mark.parametrize(
    "dates",
    [["2024-01-03", "2024-01-02"], ["2024-01-02", "2024-01-02"]],
)
def test_history_response_rejects_unordered_or_duplicate_dates(dates: list[str]) -> None:
    with pytest.raises(ValidationError, match="ascending date order without duplicates"):
        history(bars=[{**BAR, "date": day} for day in dates])


@pytest.mark.parametrize("day", ["2023-12-31", "2024-01-06"])
def test_history_response_rejects_bars_outside_the_range(day: str) -> None:
    with pytest.raises(ValidationError, match="within start and end"):
        history(bars=[{**BAR, "date": day}])


@pytest.mark.parametrize(
    "overrides", [{"fetched_at": "2024-01-06T00:00:00"}, {"source": "broker"}, {"interval": "1wk"}]
)
def test_history_response_rejects_invalid_metadata(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        history(**overrides)

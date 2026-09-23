from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.contracts import MarketHistoryQuery


def query(**overrides: object) -> MarketHistoryQuery:
    return MarketHistoryQuery(**{"symbol": "AAPL", "start": "2024-01-02", "end": "2024-01-31", **overrides})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("aapl", "AAPL"), ("  msft ", "MSFT"), ("brk-b", "BRK-B"), ("BRK.B", "BRK.B"), ("^gspc", "^GSPC"),
     ("eurusd=x", "EURUSD=X"), ("7203.T", "7203.T"), ("A" * 15, "A" * 15)],
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


@pytest.mark.parametrize("overrides", [{"interval": "1h"}, {"start": "2024-13-01"}, {"end": "yesterday"}, {"extra": "x"}])
def test_query_rejects_unsupported_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        query(**overrides)


def test_query_is_immutable() -> None:
    with pytest.raises(ValidationError):
        query().symbol = "MSFT"  # type: ignore[misc]

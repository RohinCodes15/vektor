from datetime import date
from typing import Any

import pytest
import yfinance as yf
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError, YFTzMissingError

from app.market_data import provider as provider_module
from app.market_data.errors import InvalidMarketData, MarketDataNotFound, MarketDataUnavailable
from app.market_data.provider import YFinanceProvider
from tests.market_frames import daily_frame, row

START, END = date(2024, 1, 2), date(2024, 1, 5)


class FakeTicker:
    """Stands in for yfinance.Ticker; records the history() call. No network."""

    instances: list["FakeTicker"] = []
    result: Any = None
    metadata: Any = {"currency": "USD"}

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.history_kwargs: dict[str, Any] | None = None
        FakeTicker.instances.append(self)

    def history(self, **kwargs: Any) -> Any:
        self.history_kwargs = kwargs
        if isinstance(FakeTicker.result, BaseException):
            raise FakeTicker.result
        return FakeTicker.result

    def get_history_metadata(self) -> Any:
        if isinstance(FakeTicker.metadata, BaseException):
            raise FakeTicker.metadata
        return FakeTicker.metadata


@pytest.fixture
def fake_ticker(monkeypatch: pytest.MonkeyPatch) -> type[FakeTicker]:
    FakeTicker.instances = []
    FakeTicker.result = daily_frame(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    FakeTicker.metadata = {"currency": "USD"}
    monkeypatch.setattr(provider_module.yf, "Ticker", FakeTicker)
    return FakeTicker


def test_requests_inclusive_daily_unadjusted_history(fake_ticker: type[FakeTicker]) -> None:
    history = YFinanceProvider(timeout_seconds=7).fetch_daily_history("AAPL", START, END)
    (ticker,) = fake_ticker.instances
    assert ticker.symbol == "AAPL"
    assert ticker.history_kwargs == {
        "start": "2024-01-02",
        "end": "2024-01-06",
        "interval": "1d",
        "auto_adjust": False,
        "actions": False,
        "timeout": 7,
    }
    assert history.currency == "USD"
    assert [bar.date for bar in history.bars] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]
    assert history.bars[0].adjusted_close == row()[4]


def test_provider_reports_its_source_and_enables_exceptions(fake_ticker: type[FakeTicker]) -> None:
    provider = YFinanceProvider()
    assert provider.source == "yahoo_finance"
    assert yf.config.debug.hide_exceptions is False


def test_returns_no_bars_for_an_empty_frame(fake_ticker: type[FakeTicker]) -> None:
    fake_ticker.result = daily_frame([])
    assert YFinanceProvider().fetch_daily_history("AAPL", START, END).bars == ()


@pytest.mark.parametrize(
    "error", [YFPricesMissingError("NOPE", " (1d 2024-01-02 -> 2024-01-06)"), YFTzMissingError("NOPE")]
)
def test_missing_symbols_or_prices_are_not_found(fake_ticker: type[FakeTicker], error: Exception) -> None:
    fake_ticker.result = error
    with pytest.raises(MarketDataNotFound) as raised:
        YFinanceProvider().fetch_daily_history("NOPE", START, END)
    assert raised.value.message == (
        "No daily price history found for NOPE between 2024-01-02 and 2024-01-05. "
        "Check the symbol or widen the date range."
    )


def test_rate_limits_are_reported_as_unavailable(fake_ticker: type[FakeTicker]) -> None:
    fake_ticker.result = YFRateLimitError()
    with pytest.raises(MarketDataUnavailable, match="rate limiting"):
        YFinanceProvider().fetch_daily_history("AAPL", START, END)


@pytest.mark.parametrize("error", [TimeoutError("timed out"), ConnectionError("dns"), ValueError("bad payload")])
def test_network_failures_are_unavailable_without_leaking_details(
    fake_ticker: type[FakeTicker], error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    fake_ticker.result = error
    with pytest.raises(MarketDataUnavailable) as raised:
        YFinanceProvider().fetch_daily_history("AAPL", START, END)
    assert raised.value.message == "Yahoo Finance could not be reached. Try again later."
    assert str(error) not in raised.value.message
    assert any(record.exc_info for record in caplog.records)


def test_invalid_provider_data_is_rejected(fake_ticker: type[FakeTicker]) -> None:
    fake_ticker.result = daily_frame(["2024-01-02"], [row(high=1.0)])
    with pytest.raises(InvalidMarketData, match="2024-01-02"):
        YFinanceProvider().fetch_daily_history("AAPL", START, END)


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"currency": "GBp"}, "GBp"),
        ({}, None),
        ({"currency": ""}, None),
        ({"currency": 5}, None),
        (RuntimeError("x"), None),
    ],
)
def test_currency_is_reported_verbatim_or_unknown(
    fake_ticker: type[FakeTicker], metadata: Any, expected: str | None
) -> None:
    fake_ticker.metadata = metadata
    assert YFinanceProvider().fetch_daily_history("AAPL", START, END).currency == expected


class FakeHTTPError(Exception):
    """Shaped like requests/curl_cffi HTTPError: the status is on `.response`."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP Error {status}: https://query2.finance.yahoo.com/...")
        self.response = type("Response", (), {"status_code": status})()


def test_http_404_from_the_symbol_lookup_is_not_found(fake_ticker: type[FakeTicker]) -> None:
    fake_ticker.result = FakeHTTPError(404)
    with pytest.raises(MarketDataNotFound, match="No daily price history found for ZZZZ"):
        YFinanceProvider().fetch_daily_history("ZZZZ", START, END)


def test_http_429_is_rate_limited(fake_ticker: type[FakeTicker]) -> None:
    fake_ticker.result = FakeHTTPError(429)
    with pytest.raises(MarketDataUnavailable, match="rate limiting"):
        YFinanceProvider().fetch_daily_history("AAPL", START, END)


@pytest.mark.parametrize("status", [401, 500, 502])
def test_other_http_errors_are_unavailable_without_leaking_urls(fake_ticker: type[FakeTicker], status: int) -> None:
    fake_ticker.result = FakeHTTPError(status)
    with pytest.raises(MarketDataUnavailable) as raised:
        YFinanceProvider().fetch_daily_history("AAPL", START, END)
    assert raised.value.message == "Yahoo Finance could not be reached. Try again later."

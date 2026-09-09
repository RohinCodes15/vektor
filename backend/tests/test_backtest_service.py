from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.backtest.errors import BacktestNotFound, BacktestRejected
from app.backtest.service import BacktestService
from app.backtest.store import BacktestStore
from app.contracts import BacktestCreate, PriceBar
from app.market_data.cache import HistoryCache
from app.market_data.errors import InvalidMarketData, MarketDataUnavailable
from app.market_data.service import MarketDataService
from tests.fakes import FakeProvider

D = Decimal
NOW = datetime(2024, 7, 1, 15, 0, tzinfo=UTC)
FIRST_DAY = date(2024, 1, 2)


def price_bars(closes: list[float], adjustment: float = 1.0, skip: tuple[int, ...] = ()) -> list[PriceBar]:
    """One bar per day from FIRST_DAY: open = close - 1, high = close + 1, low = close - 2."""
    return [
        PriceBar(
            date=FIRST_DAY + timedelta(days=i), open=c - 1, high=c + 1, low=c - 2, close=c,
            adjusted_close=c * adjustment, volume=1000,
        )
        for i, c in enumerate(closes)
        if i not in skip
    ]


def request(**overrides: Any) -> BacktestCreate:
    body: dict[str, Any] = {
        "symbols": ["AAPL"], "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "1000",
        "strategy": {"kind": "buy_and_hold"}, **overrides,
    }
    return BacktestCreate.model_validate(body)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(price_bars([10, 12, 14]))


@pytest.fixture
def store(tmp_path: Path) -> BacktestStore:
    return BacktestStore(tmp_path / "backtests.sqlite3")


@pytest.fixture
def service(provider: FakeProvider, store: BacktestStore, tmp_path: Path) -> BacktestService:
    market_data = MarketDataService(provider, HistoryCache(tmp_path / "cache.sqlite3"), timedelta(hours=24), lambda: NOW)
    return BacktestService(store, market_data, clock=lambda: NOW)


def test_buy_and_hold_runs_on_real_bars_and_is_stored(service: BacktestService) -> None:
    result = service.run(request())
    assert (result.mode, result.currency, result.source, result.created_at) == ("paper", "USD", "yahoo_finance", NOW)
    assert (result.bars, result.first_date, result.last_date) == (3, FIRST_DAY, FIRST_DAY + timedelta(days=2))
    (trade,) = result.trades
    # Signal at the close of day 1, filled at day 2's open (12 - 1 = 11): 90 shares for 990.00.
    assert (trade.side, trade.signal_date, trade.fill_date, trade.price, trade.quantity) == (
        "buy", FIRST_DAY, FIRST_DAY + timedelta(days=1), D("11.0000"), 90,
    )
    assert [p.equity for p in result.equity_curve] == [D("1000.00"), D("1090.00"), D("1270.00")]
    assert result.metrics.final_equity == D("1270.00") and result.metrics.total_return_pct == D("27.0000")
    assert result.metrics.trades == 1 and result.metrics.win_rate_pct is None
    (position,) = result.open_positions
    assert (position.symbol, position.quantity, position.cost_basis, position.last_price) == (
        "AAPL", 90, D("990.00"), D("14.0000"),
    )
    assert (position.market_value, position.unrealized_pnl) == (D("1260.00"), D("270.00"))
    assert "Win rate is undefined: no trade was closed." in result.warnings
    assert service.get(result.id) == result
    assert [s.id for s in service.list_backtests()] == [result.id]


def test_prices_are_adjusted_for_splits_and_dividends(service: BacktestService, provider: FakeProvider) -> None:
    provider.bars = price_bars([10, 12, 14], adjustment=0.5)
    (trade,) = service.run(request()).trades
    assert trade.price == D("5.5000")  # open 11 * adjusted_close / close


def test_only_dates_every_symbol_traded_are_simulated(service: BacktestService, provider: FakeProvider) -> None:
    provider.bars_by_symbol = {"AAPL": price_bars([10, 11, 12, 13]), "MSFT": price_bars([20, 21, 22, 23], skip=(1,))}
    result = service.run(request(symbols=["AAPL", "MSFT"]))
    assert [p.date for p in result.equity_curve] == [FIRST_DAY + timedelta(days=d) for d in (0, 2, 3)]


def test_the_same_request_on_the_same_data_gives_the_same_result(
    service: BacktestService, provider: FakeProvider
) -> None:
    provider.bars = price_bars([10, 12, 11, 12, 10, 8, 9, 13, 15, 11])
    config = request(strategy={"kind": "rsi", "period": 2}, fee_per_trade="1", slippage_bps="5")
    first, second = service.run(config), service.run(config)
    assert first.id != second.id
    assert first.trades
    assert first.model_dump(exclude={"id"}) == second.model_dump(exclude={"id"})


def test_too_little_history_is_rejected_and_not_stored(service: BacktestService, store: BacktestStore) -> None:
    sma = {"kind": "sma_crossover", "fast_window": 2, "slow_window": 3}
    with pytest.raises(BacktestRejected, match="needs at least 5 trading days .* found 3"):
        service.run(request(strategy=sma))
    assert store.list_summaries() == []


def test_an_unknown_symbol_is_rejected(service: BacktestService, provider: FakeProvider) -> None:
    provider.bars = []
    with pytest.raises(BacktestRejected, match="No daily history for AAPL between 2024-01-01 and 2024-06-28"):
        service.run(request())


def test_non_usd_prices_are_rejected(service: BacktestService, provider: FakeProvider) -> None:
    provider.currency = "EUR"
    with pytest.raises(BacktestRejected, match="priced in EUR; backtests use USD only"):
        service.run(request())


def test_prices_too_small_to_trade_are_rejected(service: BacktestService, provider: FakeProvider) -> None:
    provider.bars = price_bars([10, 12, 14], adjustment=0.000001)
    with pytest.raises(BacktestRejected, match="too small to simulate"):
        service.run(request())


@pytest.mark.parametrize("error", [MarketDataUnavailable("Provider down"), InvalidMarketData("Bad bars")])
def test_market_data_failures_propagate_and_nothing_is_stored(
    service: BacktestService, provider: FakeProvider, store: BacktestStore, error: Exception
) -> None:
    provider.error = error
    with pytest.raises(type(error)):
        service.run(request())
    assert store.list_summaries() == []


def test_an_unknown_backtest_is_not_found(service: BacktestService) -> None:
    with pytest.raises(BacktestNotFound):
        service.get(uuid4())

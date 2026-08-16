import threading
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.contracts import PaperOrder, PortfolioCreate, PortfolioUpdate, PriceBar
from app.market_data.cache import HistoryCache
from app.market_data.errors import InvalidMarketData, MarketDataNotFound, MarketDataUnavailable
from app.market_data.provider import ProviderHistory
from app.market_data.service import MarketDataService
from app.portfolio.errors import DuplicateOrder, OrderRejected, PortfolioNotFound, SnapshotRejected
from app.portfolio.service import PortfolioService
from app.portfolio.store import PortfolioStore
from tests.fakes import FakeProvider, make_bar

NOW = datetime(2024, 1, 10, 15, 0, tzinfo=UTC)


class Clock:
    """Shared by the market data and portfolio services; advancing it brings in a new trading day."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def next_day(self, days: int = 1) -> None:
        self.now += timedelta(days=days)


def order(client_order_id: str = "o-1", side: str = "buy", quantity: str = "2", symbol: str = "AAPL") -> PaperOrder:
    return PaperOrder(client_order_id=client_order_id, symbol=symbol, side=side, quantity=quantity)


@pytest.fixture
def provider() -> FakeProvider:
    # Latest close in the lookback window is 2024-01-09 at 100.25; the 2023 bar is outside it.
    return FakeProvider([make_bar("2023-12-01", 50.0), make_bar("2024-01-08", 99.0), make_bar("2024-01-09", 100.25)])


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(provider: FakeProvider, tmp_path: Path, clock: Clock) -> PortfolioService:
    market = MarketDataService(provider, HistoryCache(tmp_path / "cache.sqlite3"), timedelta(hours=24), clock=clock)
    return PortfolioService(PortfolioStore(tmp_path / "portfolios.sqlite3"), market, clock=clock)


@pytest.fixture
def portfolio_id(service: PortfolioService) -> object:
    return service.create(PortfolioCreate(name="Main", starting_cash=Decimal("1000.00"))).id


def test_crud(service: PortfolioService) -> None:
    created = service.create(PortfolioCreate(name="Main", starting_cash=Decimal("250.00")))
    assert created.created_at == NOW and created.mode == "paper"
    assert service.get(created.id) == created
    assert service.list_portfolios() == [created]
    assert service.update(created.id, PortfolioUpdate(name="Renamed")).name == "Renamed"
    service.delete(created.id)
    assert service.list_portfolios() == []


@pytest.mark.parametrize(
    "call",
    [
        lambda s, i: s.get(i),
        lambda s, i: s.update(i, PortfolioUpdate(name="x")),
        lambda s, i: s.delete(i),
        lambda s, i: s.holdings(i),
        lambda s, i: s.transactions(i),
        lambda s, i: s.submit_order(i, order()),
    ],
)
def test_unknown_portfolios_raise_not_found(service: PortfolioService, provider: FakeProvider, call: object) -> None:
    missing = uuid4()
    with pytest.raises(PortfolioNotFound, match=f"Portfolio {missing} not found."):
        call(service, missing)  # type: ignore[operator]
    assert provider.calls == []


def test_order_executes_at_the_latest_completed_close(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object
) -> None:
    provider.bars.append(make_bar("2024-01-10", 120.0))  # today's bar is still in progress and never used
    transaction, executed = service.submit_order(portfolio_id, order())  # type: ignore[arg-type]
    assert executed is True
    assert (transaction.price, transaction.price_date, transaction.notional) == (
        Decimal("100.2500"), date(2024, 1, 9), Decimal("200.50"),
    )
    assert transaction.executed_at == NOW
    assert provider.calls == [("AAPL", date(2023, 12, 27), date(2024, 1, 9))]
    assert service.get(portfolio_id).cash == Decimal("799.50")  # type: ignore[arg-type]


def test_orders_on_the_same_day_reuse_the_cached_close(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object
) -> None:
    service.submit_order(portfolio_id, order("a"))  # type: ignore[arg-type]
    second, _ = service.submit_order(portfolio_id, order("b"))  # type: ignore[arg-type]
    assert second.price == Decimal("100.2500") and len(provider.calls) == 1


def test_order_without_recent_market_data_is_rejected(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object
) -> None:
    provider.bars = [make_bar("2023-12-01", 50.0)]  # only a stale close, outside the 14-day lookback
    with pytest.raises(OrderRejected) as error:
        service.submit_order(portfolio_id, order())  # type: ignore[arg-type]
    assert error.value.message == (
        "No daily close for AAPL in the 14 days before today. Check the symbol. The order was not executed."
    )
    assert service.transactions(portfolio_id) == []  # type: ignore[arg-type]
    assert service.get(portfolio_id).cash == Decimal("1000.00")  # type: ignore[arg-type]


@pytest.mark.parametrize(("currency", "label"), [("EUR", "EUR"), ("GBp", "GBp"), (None, "an unreported currency")])
def test_order_for_a_non_usd_symbol_is_rejected(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object, currency: str | None, label: str
) -> None:
    provider.currency = currency
    with pytest.raises(OrderRejected) as error:
        service.submit_order(portfolio_id, order())  # type: ignore[arg-type]
    assert error.value.message == f"AAPL is priced in {label}; portfolios hold USD only. The order was not executed."


@pytest.mark.parametrize("failure", [MarketDataUnavailable("down"), InvalidMarketData("bad")])
def test_provider_failures_propagate_and_nothing_executes(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object, failure: Exception
) -> None:
    provider.error = failure
    with pytest.raises(type(failure)):
        service.submit_order(portfolio_id, order())  # type: ignore[arg-type]
    assert service.transactions(portfolio_id) == []  # type: ignore[arg-type]


def test_insufficient_funds_and_overselling_are_rejected(service: PortfolioService, portfolio_id: object) -> None:
    with pytest.raises(OrderRejected, match="Insufficient cash"):
        service.submit_order(portfolio_id, order("big", quantity="10"))  # type: ignore[arg-type]
    service.submit_order(portfolio_id, order("buy"))  # type: ignore[arg-type]
    with pytest.raises(OrderRejected, match="Cannot sell 3 AAPL: the portfolio holds 2."):
        service.submit_order(portfolio_id, order("sell", "sell", "3"))  # type: ignore[arg-type]
    assert len(service.transactions(portfolio_id)) == 1  # type: ignore[arg-type]


def test_replay_returns_the_original_without_fetching_a_price(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object
) -> None:
    first, _ = service.submit_order(portfolio_id, order("same"))  # type: ignore[arg-type]
    provider.error = MarketDataUnavailable("down")
    again, executed = service.submit_order(portfolio_id, order("same", quantity="2.000"))  # type: ignore[arg-type]
    assert executed is False and again == first
    assert len(provider.calls) == 1
    assert service.get(portfolio_id).cash == Decimal("799.50")  # type: ignore[arg-type]


@pytest.mark.parametrize("changed", [{"quantity": "3"}, {"side": "sell"}, {"symbol": "MSFT"}])
def test_reusing_a_client_order_id_for_a_different_order_conflicts(
    service: PortfolioService, portfolio_id: object, changed: dict[str, str]
) -> None:
    service.submit_order(portfolio_id, order("same"))  # type: ignore[arg-type]
    with pytest.raises(DuplicateOrder, match="'same' was already used for a different order"):
        service.submit_order(portfolio_id, order("same", **changed))  # type: ignore[arg-type]
    assert len(service.transactions(portfolio_id)) == 1  # type: ignore[arg-type]


def test_a_duplicate_that_wins_the_race_is_replayed(
    service: PortfolioService, portfolio_id: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _ = service.submit_order(portfolio_id, order("same"))  # type: ignore[arg-type]
    # Simulate a concurrent request: the pre-check misses, the check inside the write transaction catches it.
    monkeypatch.setattr(service._store, "find_order", lambda *_: None)
    again, executed = service.submit_order(portfolio_id, order("same"))  # type: ignore[arg-type]
    assert executed is False and again == first
    with pytest.raises(DuplicateOrder):
        service.submit_order(portfolio_id, order("same", quantity="1"))  # type: ignore[arg-type]


def test_portfolio_deleted_while_pricing_raises_not_found(
    service: PortfolioService, portfolio_id: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = service._store
    original = service._latest_quote

    def quote_then_delete(symbol: str) -> object:
        result = original(symbol)
        store.delete(portfolio_id)  # type: ignore[arg-type]
        return result

    monkeypatch.setattr(service, "_latest_quote", quote_then_delete)
    with pytest.raises(PortfolioNotFound):
        service.submit_order(portfolio_id, order())  # type: ignore[arg-type]


def test_holdings_value_positions_at_the_latest_close(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object, clock: Clock
) -> None:
    service.submit_order(portfolio_id, order("b1", quantity="4"))  # type: ignore[arg-type]  # 401.00 at 100.25
    service.submit_order(portfolio_id, order("s1", "sell", "1"))  # type: ignore[arg-type]  # realizes 0.00
    clock.next_day()
    provider.bars.append(make_bar("2024-01-10", 110.0))
    holdings = service.holdings(portfolio_id)  # type: ignore[arg-type]
    assert holdings.cash == Decimal("699.25")
    assert holdings.positions_value == Decimal("330.00")
    assert holdings.equity == Decimal("1029.25")
    assert holdings.unrealized_pnl == Decimal("29.25")  # 330.00 - 300.75 basis
    assert holdings.realized_pnl == Decimal("0.00")
    assert holdings.cash_allocation_pct == Decimal("67.94")
    assert holdings.valued_at == NOW + timedelta(days=1)
    (aapl,) = holdings.holdings
    assert (aapl.quantity, aapl.cost_basis, aapl.last_price, aapl.price_date) == (
        Decimal(3), Decimal("300.75"), Decimal("110.0000"), date(2024, 1, 10),
    )
    assert (aapl.market_value, aapl.unrealized_pnl, aapl.allocation_pct) == (
        Decimal("330.00"), Decimal("29.25"), Decimal("32.06"),
    )


def test_holdings_report_missing_prices_as_null(
    service: PortfolioService, portfolio_id: object, clock: Clock
) -> None:
    service.submit_order(portfolio_id, order())  # type: ignore[arg-type]
    clock.next_day(30)  # e.g. delisted: no close in the lookback window any more
    holdings = service.holdings(portfolio_id)  # type: ignore[arg-type]
    assert (holdings.equity, holdings.positions_value, holdings.unrealized_pnl) == (None, None, None)
    assert holdings.cash == Decimal("799.50")
    assert holdings.holdings[0].last_price is None and holdings.holdings[0].market_value is None


def test_holdings_fail_when_the_provider_is_down(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object, clock: Clock
) -> None:
    service.submit_order(portfolio_id, order())  # type: ignore[arg-type]
    clock.next_day()
    provider.error = MarketDataUnavailable("down")
    with pytest.raises(MarketDataUnavailable):
        service.holdings(portfolio_id)  # type: ignore[arg-type]


def test_holdings_of_a_cash_only_portfolio_need_no_market_data(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object
) -> None:
    holdings = service.holdings(portfolio_id)  # type: ignore[arg-type]
    assert (holdings.equity, holdings.cash_allocation_pct, holdings.holdings) == (
        Decimal("1000.00"), Decimal("100.00"), [],
    )
    assert provider.calls == []


def test_snapshot_records_equity_at_the_latest_close(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object, clock: Clock
) -> None:
    service.submit_order(portfolio_id, order(quantity="4"))  # type: ignore[arg-type]  # 401.00 at 100.25
    clock.next_day()
    provider.bars.append(make_bar("2024-01-10", 110.0))
    snapshot = service.snapshot(portfolio_id)  # type: ignore[arg-type]
    assert (snapshot.cash, snapshot.positions_value, snapshot.equity, snapshot.net_deposits) == (
        Decimal("599.00"), Decimal("440.00"), Decimal("1039.00"), Decimal("1000.00"),
    )
    assert (snapshot.realized_pnl, snapshot.unrealized_pnl, snapshot.prices_as_of) == (
        Decimal("0.00"), Decimal("39.00"), date(2024, 1, 10),
    )
    assert snapshot.taken_at == NOW + timedelta(days=1)
    assert service.equity_history(portfolio_id)[-1] == snapshot  # type: ignore[arg-type]


def test_snapshot_of_a_cash_only_portfolio_needs_no_market_data(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object
) -> None:
    snapshot = service.snapshot(portfolio_id)  # type: ignore[arg-type]
    assert (snapshot.equity, snapshot.positions_value, snapshot.prices_as_of) == (
        Decimal("1000.00"), Decimal("0.00"), None,
    )
    assert provider.calls == []


def test_snapshot_with_a_missing_price_is_refused_and_nothing_is_stored(
    service: PortfolioService, portfolio_id: object, clock: Clock
) -> None:
    service.submit_order(portfolio_id, order())  # type: ignore[arg-type]
    clock.next_day(30)
    with pytest.raises(SnapshotRejected) as error:
        service.snapshot(portfolio_id)  # type: ignore[arg-type]
    assert error.value.message == "No recent price for AAPL; the equity snapshot was not recorded."
    assert len(service.equity_history(portfolio_id)) == 1  # type: ignore[arg-type]  # only the initial snapshot


def test_snapshot_fails_and_stores_nothing_when_the_provider_is_down(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object, clock: Clock
) -> None:
    service.submit_order(portfolio_id, order())  # type: ignore[arg-type]
    clock.next_day()
    provider.error = MarketDataUnavailable("down")
    with pytest.raises(MarketDataUnavailable):
        service.snapshot(portfolio_id)  # type: ignore[arg-type]
    assert len(service.equity_history(portfolio_id)) == 1  # type: ignore[arg-type]


def test_analytics_of_a_new_portfolio(service: PortfolioService, provider: FakeProvider, portfolio_id: object) -> None:
    analytics = service.analytics(portfolio_id)  # type: ignore[arg-type]
    assert (analytics.snapshots, analytics.daily_observations, analytics.as_of) == (1, 1, NOW)
    assert (analytics.equity, analytics.net_deposits, analytics.total_return_pct) == (
        Decimal("1000.00"), Decimal("1000.00"), Decimal("0.0000"),
    )
    assert (analytics.latest_daily_return_pct, analytics.volatility_pct, analytics.sharpe_ratio,
            analytics.max_drawdown_pct) == (None, None, None, None)
    assert provider.calls == []


def test_analytics_over_several_days(
    service: PortfolioService, provider: FakeProvider, portfolio_id: object, clock: Clock
) -> None:
    service.submit_order(portfolio_id, order(quantity="4"))  # type: ignore[arg-type]  # 4 shares at 100.25
    for day, close in (("2024-01-10", 110.0), ("2024-01-11", 99.0), ("2024-01-12", 104.0)):
        clock.next_day()
        provider.bars.append(make_bar(day, close))
        service.snapshot(portfolio_id)  # type: ignore[arg-type]
    analytics = service.analytics(portfolio_id)  # type: ignore[arg-type]
    # Daily equity: 1000.00 (creation), 1039.00, 995.00, 1015.00.
    assert (analytics.snapshots, analytics.daily_observations) == (4, 4)
    assert analytics.equity == Decimal("1015.00")
    assert analytics.unrealized_pnl == Decimal("15.00") and analytics.realized_pnl == Decimal("0.00")
    assert analytics.total_return_pct == Decimal("1.5000")
    assert analytics.latest_daily_return_pct == Decimal("2.0101")  # 1015 / 995 - 1
    assert analytics.max_drawdown_pct == Decimal("-4.2348")  # 995 / 1039 - 1
    assert analytics.volatility_pct is not None and analytics.sharpe_ratio is not None
    assert analytics.as_of == NOW + timedelta(days=3)


@pytest.mark.parametrize("call", [lambda s, i: s.snapshot(i), lambda s, i: s.equity_history(i),
                                  lambda s, i: s.analytics(i)])
def test_analytics_for_unknown_portfolios_raise_not_found(service: PortfolioService, call: object) -> None:
    with pytest.raises(PortfolioNotFound):
        call(service, uuid4())  # type: ignore[operator]


class TrackingProvider(FakeProvider):
    """Records how many fetches overlap (each takes FETCH_SECONDS) and fails chosen symbols."""

    FETCH_SECONDS = 0.1

    def __init__(self, bars: list[PriceBar]) -> None:
        super().__init__(bars)
        self.errors: dict[str, Exception] = {}
        self.active = self.peak = 0
        self._lock = threading.Lock()

    def fetch_daily_history(self, symbol: str, start: date, end: date) -> ProviderHistory:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.FETCH_SECONDS)
            if symbol in self.errors:
                self.calls.append((symbol, start, end))
                raise self.errors[symbol]
            return super().fetch_daily_history(symbol, start, end)
        finally:
            with self._lock:
                self.active -= 1


@pytest.fixture
def tracked(tmp_path: Path, clock: Clock) -> tuple[PortfolioService, TrackingProvider, object]:
    """A portfolio holding AAA, BBB and CCC whose quotes are no longer cached (a new trading day)."""
    provider = TrackingProvider([make_bar("2024-01-08", 99.0), make_bar("2024-01-09", 100.25)])
    market = MarketDataService(provider, HistoryCache(tmp_path / "cache.sqlite3"), timedelta(hours=24), clock=clock)
    service = PortfolioService(PortfolioStore(tmp_path / "portfolios.sqlite3"), market, clock=clock)
    portfolio_id = service.create(PortfolioCreate(name="Main", starting_cash=Decimal("1000.00"))).id
    for symbol in ("AAA", "BBB", "CCC"):
        service.submit_order(portfolio_id, order(client_order_id=symbol, quantity="1", symbol=symbol))
    clock.next_day()
    provider.peak = 0
    return service, provider, portfolio_id


def test_holdings_fetch_uncached_quotes_concurrently(
    tracked: tuple[PortfolioService, TrackingProvider, object],
) -> None:
    service, provider, portfolio_id = tracked
    holdings = service.holdings(portfolio_id)  # type: ignore[arg-type]
    assert provider.peak == 3  # all three quotes in flight at once, not one after another
    assert [h.last_price for h in holdings.holdings] == [Decimal("100.25")] * 3


def test_holdings_mark_a_missing_quote_unpriced_and_keep_the_others(
    tracked: tuple[PortfolioService, TrackingProvider, object],
) -> None:
    service, provider, portfolio_id = tracked
    provider.errors = {"BBB": MarketDataNotFound("none")}
    holdings = service.holdings(portfolio_id)  # type: ignore[arg-type]
    assert [h.last_price for h in holdings.holdings] == [Decimal("100.25"), None, Decimal("100.25")]
    assert holdings.equity is None


def test_holdings_fail_when_any_quote_provider_request_fails(
    tracked: tuple[PortfolioService, TrackingProvider, object],
) -> None:
    service, provider, portfolio_id = tracked
    provider.errors = {"BBB": MarketDataNotFound("none"), "CCC": InvalidMarketData("bad bar")}
    with pytest.raises(InvalidMarketData, match="bad bar"):
        service.holdings(portfolio_id)  # type: ignore[arg-type]

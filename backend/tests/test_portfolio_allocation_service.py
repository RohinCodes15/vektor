from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from app.contracts import PaperOrder, PortfolioCreate, PriceBar
from app.market_data.cache import HistoryCache
from app.market_data.errors import MarketDataUnavailable
from app.market_data.service import MarketDataService
from app.portfolio.service import MIN_RISK_OBSERVATIONS, PortfolioService
from app.portfolio.store import PortfolioStore
from tests.fakes import FakeProvider, make_bar

NOW = datetime(2024, 1, 10, 15, 0, tzinfo=UTC)
LAST_CLOSE = date(2024, 1, 9)


def daily_bars(closes: list[float], last: date = LAST_CLOSE) -> list[PriceBar]:
    """One bar per calendar day, ending on `last`."""
    first = last - timedelta(days=len(closes) - 1)
    return [make_bar((first + timedelta(days=i)).isoformat(), close) for i, close in enumerate(closes)]


def zigzag(n: int, base: float, step: float) -> list[float]:
    return [base + (step if i % 2 else 0) + i * 0.1 for i in range(n)]


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(
        bars_by_symbol={
            "AAPL": daily_bars(zigzag(30, 100, 3) + [100.0]),
            "MSFT": daily_bars(zigzag(30, 50, -1) + [50.0]),
        }
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(provider: FakeProvider, tmp_path: Path, clock: Clock) -> PortfolioService:
    market = MarketDataService(provider, HistoryCache(tmp_path / "cache.sqlite3"), timedelta(hours=24), clock=clock)
    return PortfolioService(PortfolioStore(tmp_path / "portfolios.sqlite3"), market, clock=clock)


@pytest.fixture
def portfolio_id(service: PortfolioService) -> UUID:
    return service.create(PortfolioCreate(name="Main", starting_cash=Decimal("1000.00"))).id


def buy(service: PortfolioService, portfolio_id: UUID, symbol: str, quantity: str) -> None:
    order = PaperOrder(client_order_id=f"{symbol}-{quantity}", symbol=symbol, side="buy", quantity=quantity)
    service.submit_order(portfolio_id, order)


def test_allocation_weights_cash_and_concentration(service: PortfolioService, portfolio_id: UUID) -> None:
    buy(service, portfolio_id, "AAPL", "6")  # 600.00
    buy(service, portfolio_id, "MSFT", "2")  # 100.00, leaving 300.00 cash
    allocation = service.allocation(portfolio_id)
    assert allocation.status == "available" and allocation.unavailable_reason is None
    assert (allocation.cash, allocation.positions_value, allocation.equity) == (
        Decimal("300.00"), Decimal("700.00"), Decimal("1000.00"),
    )
    assert allocation.cash_weight_pct == Decimal("30.0000")
    weights = {a.symbol: (a.weight_pct, a.position_weight_pct) for a in allocation.assets}
    assert weights == {
        "AAPL": (Decimal("60.0000"), Decimal("85.7143")),
        "MSFT": (Decimal("10.0000"), Decimal("14.2857")),
    }
    assert (allocation.top_holding_symbol, allocation.top_holding_pct) == ("AAPL", Decimal("85.7143"))
    assert allocation.hhi == Decimal("0.7551")  # (6/7)^2 + (1/7)^2
    assert allocation.prices_as_of == LAST_CLOSE
    assert allocation.unpriced_symbols == allocation.stale_symbols == []


def test_cash_only_allocation_is_unavailable_but_reports_cash(service: PortfolioService, portfolio_id: UUID) -> None:
    allocation = service.allocation(portfolio_id)
    assert allocation.status == "unavailable"
    assert allocation.unavailable_reason is not None and "only cash" in allocation.unavailable_reason
    assert allocation.cash_weight_pct == Decimal("100.0000")
    assert allocation.assets == [] and allocation.hhi is None and allocation.top_holding_pct is None


def test_unpriced_holding_makes_every_weight_unknown(
    service: PortfolioService, provider: FakeProvider, portfolio_id: UUID, clock: Clock
) -> None:
    buy(service, portfolio_id, "AAPL", "1")
    buy(service, portfolio_id, "MSFT", "1")
    provider.bars_by_symbol["MSFT"] = []
    clock.now += timedelta(days=1)  # next day: completed-day prices are refetched
    allocation = service.allocation(portfolio_id)
    assert allocation.status == "unavailable" and allocation.unpriced_symbols == ["MSFT"]
    assert allocation.equity is None and allocation.cash_weight_pct is None and allocation.hhi is None
    assert all(a.weight_pct is None and a.position_weight_pct is None for a in allocation.assets)
    assert next(a for a in allocation.assets if a.symbol == "AAPL").last_price is not None


def test_old_prices_are_flagged_stale(service: PortfolioService, portfolio_id: UUID, clock: Clock) -> None:
    buy(service, portfolio_id, "AAPL", "1")
    clock.now += timedelta(days=5)  # latest close is now 6 days old
    allocation = service.allocation(portfolio_id)
    assert allocation.status == "available"
    assert allocation.stale_symbols == ["AAPL"] and allocation.assets[0].stale


def test_risk_with_enough_aligned_history(service: PortfolioService, portfolio_id: UUID) -> None:
    buy(service, portfolio_id, "AAPL", "6")
    buy(service, portfolio_id, "MSFT", "2")
    risk = service.risk(portfolio_id)
    assert risk.status == "available" and risk.unavailable_reason is None
    assert risk.observations == 30 and risk.returns_as_of == LAST_CLOSE
    assert risk.portfolio_volatility_pct is not None and risk.portfolio_volatility_pct > 0
    assert [a.symbol for a in risk.assets] == ["AAPL", "MSFT"]
    assert [a.weight_pct for a in risk.assets] == [Decimal("60.0000"), Decimal("10.0000")]
    contributions = sum(a.volatility_contribution_pct or 0 for a in risk.assets)
    assert abs(contributions - risk.portfolio_volatility_pct) <= Decimal("0.0002")
    assert abs(sum(a.contribution_share_pct or 0 for a in risk.assets) - 100) <= Decimal("0.0002")
    (pair,) = risk.correlations
    assert (pair.symbol_a, pair.symbol_b) == ("AAPL", "MSFT")
    assert pair.correlation is not None and pair.correlation < 0  # the zigzags move in opposite directions


def test_risk_is_unavailable_for_cash_only(service: PortfolioService, portfolio_id: UUID) -> None:
    risk = service.risk(portfolio_id)
    assert risk.status == "unavailable" and risk.portfolio_volatility_pct is None
    assert risk.unavailable_reason == "The portfolio holds only cash; there are no asset returns."
    assert risk.assets == [] and risk.correlations == []


def test_risk_needs_enough_aligned_returns(
    service: PortfolioService, provider: FakeProvider, portfolio_id: UUID
) -> None:
    provider.bars_by_symbol["MSFT"] = daily_bars(zigzag(MIN_RISK_OBSERVATIONS, 50, 1))  # 19 returns
    buy(service, portfolio_id, "AAPL", "1")
    buy(service, portfolio_id, "MSFT", "1")
    risk = service.risk(portfolio_id)
    assert risk.status == "unavailable" and risk.observations == MIN_RISK_OBSERVATIONS - 1
    assert risk.unavailable_reason is not None and "at least 20" in risk.unavailable_reason
    assert risk.portfolio_volatility_pct is None and risk.correlations == []


def test_misaligned_history_counts_only_shared_dates(
    service: PortfolioService, provider: FakeProvider, portfolio_id: UUID
) -> None:
    provider.bars_by_symbol["MSFT"] = daily_bars(zigzag(31, 50, 1))[::2]  # every other day
    buy(service, portfolio_id, "AAPL", "1")
    buy(service, portfolio_id, "MSFT", "1")
    risk = service.risk(portfolio_id)
    assert risk.status == "unavailable" and risk.observations == 15


def test_risk_is_unavailable_when_shared_history_is_stale(
    service: PortfolioService, provider: FakeProvider, portfolio_id: UUID, clock: Clock
) -> None:
    buy(service, portfolio_id, "AAPL", "1")
    clock.now += timedelta(days=5)
    risk = service.risk(portfolio_id)
    assert risk.status == "unavailable" and risk.observations == 30
    assert risk.unavailable_reason is not None and "stale" in risk.unavailable_reason


def test_risk_is_unavailable_when_a_holding_is_unpriced(
    service: PortfolioService, provider: FakeProvider, portfolio_id: UUID, clock: Clock
) -> None:
    buy(service, portfolio_id, "AAPL", "1")
    provider.bars_by_symbol["AAPL"] = []
    clock.now += timedelta(days=1)
    risk = service.risk(portfolio_id)
    assert risk.status == "unavailable" and risk.unavailable_reason is not None
    assert risk.unavailable_reason.startswith("No recent price for AAPL")


def test_provider_outage_propagates(service: PortfolioService, provider: FakeProvider, portfolio_id: UUID) -> None:
    buy(service, portfolio_id, "AAPL", "1")
    provider.error = MarketDataUnavailable("down")
    with pytest.raises(MarketDataUnavailable):
        service.risk(portfolio_id)

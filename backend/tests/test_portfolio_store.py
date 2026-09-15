import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import partial
from pathlib import Path
from uuid import uuid4

import pytest

from app.contracts import PaperOrder
from app.portfolio import store as store_module
from app.portfolio.accounting import Position, Quote, fill_order
from app.portfolio.errors import OrderRejected
from app.portfolio.store import PortfolioStore

NOW = datetime(2024, 1, 10, 15, 0, tzinfo=UTC)
QUOTE = Quote(Decimal("100.0000"), date(2024, 1, 9))


def order(client_order_id: str = "o-1", side: str = "buy", quantity: str = "1", symbol: str = "AAPL") -> PaperOrder:
    return PaperOrder(client_order_id=client_order_id, symbol=symbol, side=side, quantity=quantity)


def execute(store: PortfolioStore, portfolio_id: object, request: PaperOrder, quote: Quote = QUOTE) -> object:
    fill = partial(fill_order, request.side, request.symbol, request.quantity, quote.price)
    return store.execute_order(portfolio_id, request, quote, fill, NOW)  # type: ignore[arg-type]


@pytest.fixture
def store(tmp_path: Path) -> PortfolioStore:
    return PortfolioStore(tmp_path / "portfolios.sqlite3")


def test_create_get_list_rename_delete(store: PortfolioStore) -> None:
    first = store.create("First", Decimal("1000.00"), NOW)
    second = store.create("Second", Decimal("50.00"), NOW)
    assert (first.cash, first.starting_cash, first.realized_pnl, first.currency) == (
        Decimal("1000.00"), Decimal("1000.00"), Decimal("0.00"), "USD",
    )
    assert store.get(first.id) == first
    assert [p.id for p in store.list_portfolios()] == [first.id, second.id]
    later = datetime(2024, 1, 11, tzinfo=UTC)
    renamed = store.rename(first.id, "Renamed", later)
    assert renamed is not None and renamed.name == "Renamed" and renamed.updated_at == later
    assert renamed.created_at == first.created_at
    assert store.delete(first.id) is True
    assert store.get(first.id) is None and store.delete(first.id) is False
    assert store.rename(first.id, "x", later) is None


def test_amounts_round_trip_exactly(store: PortfolioStore) -> None:
    portfolio = store.create("Exact", Decimal("0.30"), NOW)
    execute(store, portfolio.id, order(quantity="0.001"), Quote(Decimal("100.1000"), date(2024, 1, 9)))
    assert store.get(portfolio.id).cash == Decimal("0.20")  # type: ignore[union-attr]
    assert store.positions(portfolio.id) == [Position("AAPL", Decimal("0.001"), Decimal("0.10"))]


def test_executed_order_updates_cash_position_and_history(store: PortfolioStore) -> None:
    portfolio = store.create("P", Decimal("1000.00"), NOW)
    transaction, executed = execute(store, portfolio.id, order(quantity="3"))  # type: ignore[misc]
    assert executed is True
    assert (transaction.symbol, transaction.side, transaction.quantity, transaction.price) == (
        "AAPL", "buy", Decimal(3), Decimal("100.0000"),
    )
    assert (transaction.notional, transaction.realized_pnl, transaction.price_date) == (
        Decimal("300.00"), None, date(2024, 1, 9),
    )
    assert store.get(portfolio.id).cash == Decimal("700.00")  # type: ignore[union-attr]
    assert store.positions(portfolio.id) == [Position("AAPL", Decimal(3), Decimal("300.00"))]
    assert store.transactions(portfolio.id) == [transaction]


def test_sells_accumulate_realized_pnl_and_closing_removes_the_position(store: PortfolioStore) -> None:
    portfolio = store.create("P", Decimal("1000.00"), NOW)
    execute(store, portfolio.id, order("b", quantity="4"))
    execute(store, portfolio.id, order("s1", "sell", "1"), Quote(Decimal(110), date(2024, 1, 9)))
    execute(store, portfolio.id, order("s2", "sell", "3"), Quote(Decimal(90), date(2024, 1, 9)))
    after = store.get(portfolio.id)
    assert after is not None
    assert after.realized_pnl == Decimal("-20.00")  # +10.00 then -30.00
    assert after.cash == Decimal("980.00")
    assert store.positions(portfolio.id) == []
    assert [t.client_order_id for t in store.transactions(portfolio.id)] == ["b", "s1", "s2"]


def test_rejected_order_changes_nothing(store: PortfolioStore) -> None:
    portfolio = store.create("P", Decimal("50.00"), NOW)
    with pytest.raises(OrderRejected, match="Insufficient cash"):
        execute(store, portfolio.id, order(quantity="1"))
    with pytest.raises(OrderRejected, match="holds none"):
        execute(store, portfolio.id, order("o-2", "sell"))
    assert store.get(portfolio.id) == portfolio
    assert store.positions(portfolio.id) == [] and store.transactions(portfolio.id) == []


def test_a_failure_mid_write_rolls_back_every_change(store: PortfolioStore, monkeypatch: pytest.MonkeyPatch) -> None:
    portfolio = store.create("P", Decimal("1000.00"), NOW)

    def broken(*_: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store_module, "_save_position", broken)
    with pytest.raises(sqlite3.OperationalError):
        execute(store, portfolio.id, order())
    assert store.get(portfolio.id) == portfolio  # the cash update before the failure was rolled back
    assert store.transactions(portfolio.id) == []


def test_reusing_a_client_order_id_returns_the_original_without_executing(store: PortfolioStore) -> None:
    portfolio = store.create("P", Decimal("1000.00"), NOW)
    first, _ = execute(store, portfolio.id, order("same"))  # type: ignore[misc]
    again, executed = execute(store, portfolio.id, order("same"))  # type: ignore[misc]
    assert executed is False and again == first
    assert store.get(portfolio.id).cash == Decimal("900.00")  # type: ignore[union-attr]
    assert store.find_order(portfolio.id, "same") == first
    assert store.find_order(portfolio.id, "other") is None


def test_client_order_ids_are_scoped_to_a_portfolio(store: PortfolioStore) -> None:
    one = store.create("One", Decimal("1000.00"), NOW)
    two = store.create("Two", Decimal("1000.00"), NOW)
    assert execute(store, one.id, order("same"))[1] is True  # type: ignore[index]
    assert execute(store, two.id, order("same"))[1] is True  # type: ignore[index]


def test_order_for_a_missing_portfolio_returns_none(store: PortfolioStore) -> None:
    assert execute(store, uuid4(), order()) is None


def test_concurrent_orders_never_overdraw_cash(store: PortfolioStore) -> None:
    portfolio = store.create("P", Decimal("500.00"), NOW)

    def buy(index: int) -> bool:
        try:
            execute(store, portfolio.id, order(f"o-{index}"))
        except OrderRejected:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(buy, range(20)))
    assert results.count(True) == 5
    assert store.get(portfolio.id).cash == Decimal("0.00")  # type: ignore[union-attr]
    assert store.positions(portfolio.id) == [Position("AAPL", Decimal(5), Decimal("500.00"))]
    assert len(store.transactions(portfolio.id)) == 5


def test_concurrent_duplicates_execute_once(store: PortfolioStore) -> None:
    portfolio = store.create("P", Decimal("1000.00"), NOW)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: execute(store, portfolio.id, order("dup")), range(10)))
    assert sum(executed for _, executed in results) == 1  # type: ignore[misc]
    assert len({transaction.id for transaction, _ in results}) == 1  # type: ignore[misc]
    assert store.get(portfolio.id).cash == Decimal("900.00")  # type: ignore[union-attr]


def test_delete_cascades_to_positions_and_transactions(store: PortfolioStore, tmp_path: Path) -> None:
    portfolio = store.create("P", Decimal("1000.00"), NOW)
    execute(store, portfolio.id, order())
    store.delete(portfolio.id)
    with sqlite3.connect(tmp_path / "portfolios.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone() == (0,)
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone() == (0,)


def test_data_persists_across_store_instances(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "portfolios.sqlite3"
    portfolio = PortfolioStore(path).create("P", Decimal("1000.00"), NOW)
    execute(PortfolioStore(path), portfolio.id, order())
    reopened = PortfolioStore(path)
    assert reopened.get(portfolio.id).cash == Decimal("900.00")  # type: ignore[union-attr]
    assert len(reopened.transactions(portfolio.id)) == 1


def test_create_records_an_all_cash_initial_snapshot(store: PortfolioStore) -> None:
    portfolio = store.create("P", Decimal("1000.00"), NOW)
    (initial,) = store.snapshots(portfolio.id)
    assert (initial.taken_at, initial.cash, initial.positions_value, initial.equity, initial.net_deposits) == (
        NOW, Decimal("1000.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("1000.00"),
    )
    assert (initial.realized_pnl, initial.unrealized_pnl, initial.prices_as_of) == (
        Decimal("0.00"), Decimal("0.00"), None,
    )

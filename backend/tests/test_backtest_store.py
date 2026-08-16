import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.backtest.store import BacktestStore
from app.contracts import Backtest, BacktestCreate, BacktestMetrics

NOW = datetime(2024, 7, 1, 12, 0, tzinfo=UTC)


def backtest(created_at: datetime = NOW) -> Backtest:
    config = BacktestCreate.model_validate({
        "symbols": ["AAPL"], "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "1000",
        "strategy": {"kind": "rsi"}, "fee_bps": "1.5",
    })
    metrics = BacktestMetrics(
        final_equity=Decimal("1000.00"), total_return_pct=Decimal("0.0000"), annualized_return_pct=None,
        volatility_pct=None, max_drawdown_pct=Decimal("0.0000"), sharpe_ratio=None, win_rate_pct=None, trades=0,
        closed_trades=0, winning_trades=0, total_fees=Decimal("0.00"),
    )
    return Backtest(
        id=uuid4(), currency="USD", config=config, created_at=created_at, source="yahoo_finance", bars=1,
        first_date=date(2024, 1, 2), last_date=date(2024, 1, 2), metrics=metrics, warnings=["Win rate is undefined."],
        equity_curve=[], trades=[], rejected_orders=[], open_positions=[],
    )


def test_a_stored_backtest_round_trips_exactly(tmp_path: Path) -> None:
    store = BacktestStore(tmp_path / "nested" / "backtests.sqlite3")
    original = backtest()
    store.add(original)
    assert store.get(original.id) == original
    assert store.get(uuid4()) is None


def test_summaries_list_backtests_oldest_first_without_details(tmp_path: Path) -> None:
    store = BacktestStore(tmp_path / "backtests.sqlite3")
    first, second = backtest(), backtest(NOW.replace(hour=13))
    store.add(first)
    store.add(second)
    summaries = store.list_summaries()
    assert [s.id for s in summaries] == [first.id, second.id]
    assert summaries[0].metrics == first.metrics and summaries[0].config == first.config
    assert "equity_curve" not in summaries[0].model_dump()


def test_an_empty_store_lists_nothing(tmp_path: Path) -> None:
    assert BacktestStore(tmp_path / "backtests.sqlite3").list_summaries() == []


def test_listing_reads_only_the_stored_summaries(tmp_path: Path) -> None:
    path = tmp_path / "backtests.sqlite3"
    store = BacktestStore(path)
    stored = backtest()
    store.add(stored)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("UPDATE backtests SET result = 'not parsed when listing'")
    assert [s.id for s in store.list_summaries()] == [stored.id]


def test_a_database_from_before_summaries_is_migrated_once_and_lists_the_same(tmp_path: Path) -> None:
    path = tmp_path / "backtests.sqlite3"
    old = [backtest(), backtest(NOW.replace(hour=13))]
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE backtests (seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,"
            " result TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO backtests (id, created_at, result) VALUES (?, ?, ?)",
            [(str(b.id), b.created_at.isoformat(), b.model_dump_json()) for b in old],
        )
    store = BacktestStore(path)
    summaries = store.list_summaries()
    assert [s.id for s in summaries] == [b.id for b in old]
    assert summaries[0].metrics == old[0].metrics and summaries[0].config == old[0].config
    assert store.get(old[1].id) == old[1]
    newer = backtest()
    store.add(newer)
    # A second store on the migrated database (a restarted server) sees everything, without migrating again.
    assert [s.id for s in BacktestStore(path).list_summaries()] == [*[b.id for b in old], newer.id]

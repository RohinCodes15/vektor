"""SQLite persistence for completed backtests. Each result is stored whole as its JSON contract, so it round-trips
exactly (Decimals are JSON strings) and a stored backtest is never recomputed.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import UUID

from app.contracts import Backtest, BacktestSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS backtests (
    seq INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    result TEXT NOT NULL
);
"""
CONNECT_TIMEOUT_SECONDS = 5


class BacktestStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def add(self, backtest: Backtest) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO backtests (id, created_at, result) VALUES (?, ?, ?)",
                (str(backtest.id), backtest.created_at.isoformat(), backtest.model_dump_json()),
            )

    def get(self, backtest_id: UUID) -> Backtest | None:
        with self._connect() as conn:
            row = conn.execute("SELECT result FROM backtests WHERE id = ?", (str(backtest_id),)).fetchone()
        return Backtest.model_validate_json(row[0]) if row else None

    def list_summaries(self) -> list[BacktestSummary]:
        """Every stored backtest without its curve and trades, oldest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT result FROM backtests ORDER BY seq").fetchall()
        return [_summary(Backtest.model_validate_json(row[0])) for row in rows]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """One connection; the `with conn` block commits on success and rolls back on any exception."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path, timeout=CONNECT_TIMEOUT_SECONDS)) as conn:
            conn.executescript(SCHEMA)
            with conn:
                yield conn


def _summary(backtest: Backtest) -> BacktestSummary:
    return BacktestSummary(
        id=backtest.id,
        created_at=backtest.created_at,
        config=backtest.config,
        bars=backtest.bars,
        first_date=backtest.first_date,
        last_date=backtest.last_date,
        metrics=backtest.metrics,
    )

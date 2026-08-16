"""SQLite persistence for completed backtests. Each result is stored whole as its JSON contract, so it round-trips
exactly (Decimals are JSON strings) and a stored backtest is never recomputed.

Its summary (the result without curve, trades and positions) is stored beside it, so listing backtests reads a
few hundred bytes per row instead of parsing every full result. Databases created before the summary column existed
are migrated, and their summaries filled from the stored results, the first time a store opens them.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.contracts import Backtest, BacktestSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS backtests (
    seq INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    result TEXT NOT NULL,
    summary TEXT
);
"""
CONNECT_TIMEOUT_SECONDS = 5


class BacktestStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._migrated = False
        self._migrate_lock = Lock()

    def add(self, backtest: Backtest) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO backtests (id, created_at, result, summary) VALUES (?, ?, ?, ?)",
                (str(backtest.id), backtest.created_at.isoformat(), backtest.model_dump_json(),
                 _summary(backtest).model_dump_json()),
            )

    def get(self, backtest_id: UUID) -> Backtest | None:
        with self._connect() as conn:
            row = conn.execute("SELECT result FROM backtests WHERE id = ?", (str(backtest_id),)).fetchone()
        return Backtest.model_validate_json(row[0]) if row else None

    def list_summaries(self) -> list[BacktestSummary]:
        """Every stored backtest without its curve and trades, oldest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT summary FROM backtests ORDER BY seq").fetchall()
        return [BacktestSummary.model_validate_json(row[0]) for row in rows]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """One connection; the `with conn` block commits on success and rolls back on any exception."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path, timeout=CONNECT_TIMEOUT_SECONDS)) as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)
            with conn:
                yield conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add and fill the summary column of a database created before it existed. Once per store."""
        if self._migrated:
            return
        with self._migrate_lock:
            if self._migrated:
                return
            with conn:  # a failed backfill rolls back and is retried on the next connection
                columns = {row[1] for row in conn.execute("PRAGMA table_info(backtests)")}
                if "summary" not in columns:
                    _add_summary_column(conn)
                missing = conn.execute("SELECT seq, result FROM backtests WHERE summary IS NULL").fetchall()
                conn.executemany(
                    "UPDATE backtests SET summary = ? WHERE seq = ?",
                    [(_summary(Backtest.model_validate_json(r)).model_dump_json(), seq) for seq, r in missing],
                )
            self._migrated = True


def _add_summary_column(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ALTER TABLE backtests ADD COLUMN summary TEXT")
    except sqlite3.OperationalError as error:
        if "duplicate column" not in str(error):  # another server process migrated it first
            raise


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

"""Local SQLite cache of provider responses.

Each entry is one complete provider response for [start_date, end_date]. A request is served only from a single
fresh entry that covers its whole range, so cached history is never stitched together from fetches made at
different times (which could mix price adjustments before and after a split or dividend).
"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.contracts import MarketHistoryQuery, MarketHistoryResponse, PriceBar

SCHEMA = """
CREATE TABLE IF NOT EXISTS history_fetches (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    currency TEXT,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_fetches_lookup ON history_fetches (source, symbol, interval, fetched_at);
CREATE TABLE IF NOT EXISTS history_bars (
    fetch_id INTEGER NOT NULL REFERENCES history_fetches (id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    adjusted_close REAL NOT NULL,
    volume INTEGER NOT NULL,
    PRIMARY KEY (fetch_id, date)
) WITHOUT ROWID;
"""

BAR_COLUMNS = ("date", "open", "high", "low", "close", "adjusted_close", "volume")
CONNECT_TIMEOUT_SECONDS = 5


class HistoryCache:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self, query: MarketHistoryQuery, source: str, fresh_after: datetime) -> MarketHistoryResponse | None:
        """The newest entry fetched at or after `fresh_after` that covers the query, trimmed to its range."""
        with closing(self._connect()) as conn:
            entry = conn.execute(
                """
                SELECT id, currency, fetched_at FROM history_fetches
                WHERE source = ? AND symbol = ? AND interval = ? AND start_date <= ? AND end_date >= ?
                  AND fetched_at >= ?
                ORDER BY fetched_at DESC, id DESC LIMIT 1
                """,
                (source, query.symbol, query.interval, query.start.isoformat(), query.end.isoformat(),
                 _timestamp(fresh_after)),
            ).fetchone()
            if entry is None:
                return None
            fetch_id, currency, fetched_at = entry
            rows = conn.execute(
                f"SELECT {', '.join(BAR_COLUMNS)} FROM history_bars"
                " WHERE fetch_id = ? AND date BETWEEN ? AND ? ORDER BY date",
                (fetch_id, query.start.isoformat(), query.end.isoformat()),
            ).fetchall()
        return MarketHistoryResponse(
            symbol=query.symbol,
            interval=query.interval,
            start=query.start,
            end=query.end,
            currency=currency,
            source=source,
            cached=True,
            fetched_at=datetime.fromisoformat(fetched_at),
            bars=[PriceBar(**dict(zip(BAR_COLUMNS, row, strict=True))) for row in rows],
        )

    def store(self, response: MarketHistoryResponse, expire_before: datetime) -> None:
        """Save one provider response; drop entries it supersedes and entries fetched before `expire_before`."""
        with closing(self._connect()) as conn, conn:
            fetch_id = conn.execute(
                """
                INSERT INTO history_fetches (source, symbol, interval, start_date, end_date, currency, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (response.source, response.symbol, response.interval, response.start.isoformat(),
                 response.end.isoformat(), response.currency, _timestamp(response.fetched_at)),
            ).lastrowid
            conn.executemany(
                f"INSERT INTO history_bars (fetch_id, {', '.join(BAR_COLUMNS)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(fetch_id, bar.date.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.adjusted_close,
                  bar.volume) for bar in response.bars],
            )
            conn.execute(
                """
                DELETE FROM history_fetches WHERE id != ? AND (
                    fetched_at < ?
                    OR (source = ? AND symbol = ? AND interval = ? AND start_date >= ? AND end_date <= ?)
                )
                """,
                (fetch_id, _timestamp(expire_before), response.source, response.symbol, response.interval,
                 response.start.isoformat(), response.end.isoformat()),
            )

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, timeout=CONNECT_TIMEOUT_SECONDS)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA)
        except sqlite3.Error:
            conn.close()
            raise
        return conn


def _timestamp(moment: datetime) -> str:
    """Fixed-width UTC ISO text, so SQLite string comparison matches chronological order."""
    return moment.astimezone(UTC).isoformat(timespec="microseconds")

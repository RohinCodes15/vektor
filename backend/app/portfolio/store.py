"""SQLite persistence for paper portfolios, positions, and transactions.

Amounts are stored as decimal TEXT so they round-trip exactly. Each order executes inside one
BEGIN IMMEDIATE transaction: the duplicate check, the cash and quantity checks, and every write happen
under SQLite's write lock, so concurrent orders cannot overdraw cash, oversell, or execute twice.
"""

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from app.contracts import PaperOrder, Portfolio, Transaction
from app.portfolio.accounting import Fill, Position, Quote

SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolios (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    currency TEXT NOT NULL,
    starting_cash TEXT NOT NULL,
    cash TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    portfolio_id TEXT NOT NULL REFERENCES portfolios (id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    quantity TEXT NOT NULL,
    cost_basis TEXT NOT NULL,
    PRIMARY KEY (portfolio_id, symbol)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS transactions (
    seq INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    portfolio_id TEXT NOT NULL REFERENCES portfolios (id) ON DELETE CASCADE,
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity TEXT NOT NULL,
    price TEXT NOT NULL,
    price_date TEXT NOT NULL,
    notional TEXT NOT NULL,
    realized_pnl TEXT,
    executed_at TEXT NOT NULL,
    UNIQUE (portfolio_id, client_order_id)
);
"""

PORTFOLIO_COLUMNS = ("id", "name", "currency", "starting_cash", "cash", "realized_pnl", "created_at", "updated_at")
TRANSACTION_COLUMNS = (
    "id", "portfolio_id", "client_order_id", "symbol", "side", "quantity", "price", "price_date", "notional",
    "realized_pnl", "executed_at",
)
CONNECT_TIMEOUT_SECONDS = 5

# Applies a fill to (cash, position); raises OrderRejected to roll the order back.
FillFunction = Callable[[Decimal, Position | None], Fill]


class PortfolioStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def create(self, name: str, starting_cash: Decimal, now: datetime) -> Portfolio:
        stamp = _timestamp(now)
        values = (str(uuid4()), name, "USD", str(starting_cash), str(starting_cash), "0.00", stamp, stamp)
        with self._write() as conn:
            conn.execute(f"INSERT INTO portfolios ({', '.join(PORTFOLIO_COLUMNS)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values)
        return _portfolio(values)

    def list_portfolios(self) -> list[Portfolio]:
        with self._read() as conn:
            rows = conn.execute(f"SELECT {', '.join(PORTFOLIO_COLUMNS)} FROM portfolios ORDER BY created_at, rowid")
            return [_portfolio(row) for row in rows]

    def get(self, portfolio_id: UUID) -> Portfolio | None:
        with self._read() as conn:
            return _get_portfolio(conn, portfolio_id)

    def rename(self, portfolio_id: UUID, name: str, now: datetime) -> Portfolio | None:
        with self._write() as conn:
            conn.execute(
                "UPDATE portfolios SET name = ?, updated_at = ? WHERE id = ?", (name, _timestamp(now), str(portfolio_id))
            )
            return _get_portfolio(conn, portfolio_id)

    def delete(self, portfolio_id: UUID) -> bool:
        """Delete the portfolio with its positions and transactions. False if it did not exist."""
        with self._write() as conn:
            return conn.execute("DELETE FROM portfolios WHERE id = ?", (str(portfolio_id),)).rowcount == 1

    def positions(self, portfolio_id: UUID) -> list[Position]:
        with self._read() as conn:
            return _positions(conn, portfolio_id)

    def transactions(self, portfolio_id: UUID) -> list[Transaction]:
        with self._read() as conn:
            rows = conn.execute(
                f"SELECT {', '.join(TRANSACTION_COLUMNS)} FROM transactions WHERE portfolio_id = ? ORDER BY seq",
                (str(portfolio_id),),
            )
            return [_transaction(row) for row in rows]

    def find_order(self, portfolio_id: UUID, client_order_id: str) -> Transaction | None:
        with self._read() as conn:
            return _find_order(conn, portfolio_id, client_order_id)

    def execute_order(
        self, portfolio_id: UUID, order: PaperOrder, quote: Quote, fill: FillFunction, now: datetime
    ) -> tuple[Transaction, bool] | None:
        """Atomically apply `fill` and record the transaction.

        Returns (transaction, True) when executed, (earlier transaction, False) when `client_order_id` was
        already used, or None when the portfolio does not exist. Exceptions from `fill` roll everything back.
        """
        with self._write() as conn:
            portfolio = _get_portfolio(conn, portfolio_id)
            if portfolio is None:
                return None
            earlier = _find_order(conn, portfolio_id, order.client_order_id)
            if earlier is not None:
                return earlier, False
            held = next((p for p in _positions(conn, portfolio_id) if p.symbol == order.symbol), None)
            # Validates cash and quantity against the balances read under the write lock.
            result = fill(portfolio.cash, held)
            stamp = _timestamp(now)
            realized = portfolio.realized_pnl + (result.realized_pnl or 0)
            conn.execute(
                "UPDATE portfolios SET cash = ?, realized_pnl = ?, updated_at = ? WHERE id = ?",
                (str(result.cash), str(realized), stamp, str(portfolio_id)),
            )
            _save_position(conn, portfolio_id, order.symbol, result.position)
            values = (
                str(uuid4()), str(portfolio_id), order.client_order_id, order.symbol, order.side, str(order.quantity),
                str(quote.price), quote.price_date.isoformat(), str(result.notional),
                None if result.realized_pnl is None else str(result.realized_pnl), stamp,
            )
            conn.execute(
                f"INSERT INTO transactions ({', '.join(TRANSACTION_COLUMNS)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
        return _transaction(values), True

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as conn:
            yield conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """One IMMEDIATE transaction: committed on success, rolled back on any exception."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: the driver never opens transactions implicitly; _write opens them explicitly.
        conn = sqlite3.connect(self._path, timeout=CONNECT_TIMEOUT_SECONDS, isolation_level=None)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA)
        except sqlite3.Error:
            conn.close()
            raise
        return conn


def _get_portfolio(conn: sqlite3.Connection, portfolio_id: UUID) -> Portfolio | None:
    row = conn.execute(
        f"SELECT {', '.join(PORTFOLIO_COLUMNS)} FROM portfolios WHERE id = ?", (str(portfolio_id),)
    ).fetchone()
    return _portfolio(row) if row else None


def _positions(conn: sqlite3.Connection, portfolio_id: UUID) -> list[Position]:
    rows = conn.execute(
        "SELECT symbol, quantity, cost_basis FROM positions WHERE portfolio_id = ? ORDER BY symbol",
        (str(portfolio_id),),
    )
    return [Position(symbol, Decimal(quantity), Decimal(cost_basis)) for symbol, quantity, cost_basis in rows]


def _find_order(conn: sqlite3.Connection, portfolio_id: UUID, client_order_id: str) -> Transaction | None:
    row = conn.execute(
        f"SELECT {', '.join(TRANSACTION_COLUMNS)} FROM transactions WHERE portfolio_id = ? AND client_order_id = ?",
        (str(portfolio_id), client_order_id),
    ).fetchone()
    return _transaction(row) if row else None


def _save_position(conn: sqlite3.Connection, portfolio_id: UUID, symbol: str, position: Position | None) -> None:
    if position is None:
        conn.execute("DELETE FROM positions WHERE portfolio_id = ? AND symbol = ?", (str(portfolio_id), symbol))
        return
    conn.execute(
        """
        INSERT INTO positions (portfolio_id, symbol, quantity, cost_basis) VALUES (?, ?, ?, ?)
        ON CONFLICT (portfolio_id, symbol) DO UPDATE SET quantity = excluded.quantity, cost_basis = excluded.cost_basis
        """,
        (str(portfolio_id), symbol, str(position.quantity), str(position.cost_basis)),
    )


def _portfolio(row: tuple[str, ...]) -> Portfolio:
    return Portfolio(**dict(zip(PORTFOLIO_COLUMNS, row, strict=True)))


def _transaction(row: tuple[str | None, ...]) -> Transaction:
    return Transaction(**dict(zip(TRANSACTION_COLUMNS, row, strict=True)))


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")

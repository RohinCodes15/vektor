"""Paper portfolio arithmetic. Pure: no I/O. Every amount is a Decimal; floats never touch money.

Rounding rules (all ROUND_HALF_EVEN, applied once per computed value):
- Prices: the provider's daily close, rounded to 4 decimal places.
- Money (cash, notional, cost basis, market value, P&L): rounded to cents. A trade's notional is
  quantity * price rounded to cents, and cash moves by exactly that amount (no fees, no slippage).
- Cost basis is the average cost. Selling part of a position removes cost_basis * sold / held, rounded to cents;
  selling all of it removes the whole remaining basis, so no stray cents are left behind.
- Allocation percentages: value / equity * 100, rounded to 2 decimal places; they may not sum to exactly 100.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from app.contracts import Holding, OrderSide
from app.portfolio.errors import OrderRejected

CENT = Decimal("0.01")
PRICE_TICK = Decimal("0.0001")
PERCENT_TICK = Decimal("0.01")


def to_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, ROUND_HALF_EVEN)


def to_price(close: float) -> Decimal:
    """Exact decimal of the provider's float close (via its shortest repr), rounded to 4 places."""
    return Decimal(str(close)).quantize(PRICE_TICK, ROUND_HALF_EVEN)


def to_percent(part: Decimal, whole: Decimal) -> Decimal | None:
    return None if whole == 0 else (part * 100 / whole).quantize(PERCENT_TICK, ROUND_HALF_EVEN)


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: Decimal
    cost_basis: Decimal


@dataclass(frozen=True)
class Fill:
    """The outcome of one order: the new cash balance and position (None once fully sold)."""

    cash: Decimal
    position: Position | None
    notional: Decimal
    realized_pnl: Decimal | None


@dataclass(frozen=True)
class Quote:
    price: Decimal
    price_date: date


def fill_order(
    side: OrderSide, symbol: str, quantity: Decimal, price: Decimal, cash: Decimal, position: Position | None
) -> Fill:
    """Apply a market order at `price`, or raise OrderRejected. Never shorts and never overdraws cash."""
    notional = to_cents(quantity * price)
    if side == "buy":
        return _buy(symbol, quantity, price, notional, cash, position)
    return _sell(symbol, quantity, notional, cash, position)


def _buy(
    symbol: str, quantity: Decimal, price: Decimal, notional: Decimal, cash: Decimal, position: Position | None
) -> Fill:
    if notional == 0:
        raise OrderRejected(f"Order value rounds to $0.00: buy more than {quantity} {symbol} at {price}.")
    if notional > cash:
        raise OrderRejected(
            f"Insufficient cash: buying {quantity} {symbol} at {price} costs {notional}, available cash is {cash}."
        )
    held = position or Position(symbol, Decimal(0), Decimal("0.00"))
    new_position = Position(symbol, held.quantity + quantity, held.cost_basis + notional)
    return Fill(cash=cash - notional, position=new_position, notional=notional, realized_pnl=None)


def _sell(symbol: str, quantity: Decimal, notional: Decimal, cash: Decimal, position: Position | None) -> Fill:
    if position is None:
        raise OrderRejected(f"Cannot sell {symbol}: the portfolio holds none. Short selling is not supported.")
    if quantity > position.quantity:
        raise OrderRejected(f"Cannot sell {quantity} {symbol}: the portfolio holds {position.quantity}.")
    if quantity == position.quantity:
        sold_basis, remaining = position.cost_basis, None
    else:
        sold_basis = to_cents(position.cost_basis * quantity / position.quantity)
        remaining = Position(symbol, position.quantity - quantity, position.cost_basis - sold_basis)
    return Fill(cash=cash + notional, position=remaining, notional=notional, realized_pnl=notional - sold_basis)


@dataclass(frozen=True)
class Valuation:
    holdings: tuple[Holding, ...]
    positions_value: Decimal | None
    equity: Decimal | None
    unrealized_pnl: Decimal | None
    cash_allocation_pct: Decimal | None


def value_portfolio(cash: Decimal, positions: list[Position], quotes: dict[str, Quote | None]) -> Valuation:
    """Mark positions to `quotes`. A missing quote leaves that holding unpriced and the totals unknown."""
    values = {
        p.symbol: to_cents(p.quantity * quote.price) for p in positions if (quote := quotes.get(p.symbol)) is not None
    }
    complete = len(values) == len(positions)
    positions_value = sum(values.values(), Decimal("0.00")) if complete else None
    equity = cash + positions_value if positions_value is not None else None
    holdings = tuple(_holding(p, quotes.get(p.symbol), values.get(p.symbol), equity) for p in positions)
    return Valuation(
        holdings=holdings,
        positions_value=positions_value,
        equity=equity,
        unrealized_pnl=sum((h.unrealized_pnl for h in holdings if h.unrealized_pnl is not None), Decimal("0.00"))
        if complete
        else None,
        cash_allocation_pct=to_percent(cash, equity) if equity is not None else None,
    )


def _holding(position: Position, quote: Quote | None, value: Decimal | None, equity: Decimal | None) -> Holding:
    return Holding(
        symbol=position.symbol,
        quantity=position.quantity,
        cost_basis=position.cost_basis,
        last_price=quote.price if quote else None,
        price_date=quote.price_date if quote else None,
        market_value=value,
        unrealized_pnl=value - position.cost_basis if value is not None else None,
        allocation_pct=to_percent(value, equity) if value is not None and equity is not None else None,
    )

"""Event-driven, long-only backtest simulation. Pure: no I/O, Decimal only, deterministic.

Timeline for bar i of the shared calendar:
1. Orders from signals at the close of bar i - 1 fill at the open of bar i: sells first, then buys, each in symbol
   order. A signal therefore never fills on the bar that produced it (no look-ahead).
2. Positions are marked at the close of bar i.
3. Signals at the close of bar i become orders for bar i + 1. A signal on the last bar never fills.

Execution rules (also in backend/README.md):
- Buys fill at open * (1 + slippage), rounded up to 4 places and capped at the bar's high; sells at
  open * (1 - slippage), rounded down and floored at the bar's low. A fill never leaves the bar's traded range.
- Every fill pays fee_per_trade + notional * fee_rate, rounded to cents. Notional is quantity * price in cents.
- Whole shares only, long only. A buy targets equity at the previous close * position_fraction / number of symbols,
  limited to the cash on hand, and takes the largest whole quantity whose notional + fee fits. A sell closes the
  whole position. An order that cannot fill (less than one share affordable, or a sell whose fee exceeds its proceeds
  plus cash) is rejected and changes nothing, so cash never goes negative.
- A buy signal while holding the symbol, or a sell signal while flat, is ignored.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from app.backtest.prices import Bar
from app.backtest.strategies import Signal
from app.portfolio.accounting import PRICE_TICK, to_cents

ONE = Decimal(1)
ZERO_CASH = Decimal("0.00")


@dataclass(frozen=True)
class Costs:
    fee_per_trade: Decimal  # dollars per fill
    fee_rate: Decimal  # fraction of notional
    slippage: Decimal  # fraction of the open price

    def fee(self, notional: Decimal) -> Decimal:
        return to_cents(self.fee_per_trade + notional * self.fee_rate)


@dataclass(frozen=True)
class Order:
    symbol: str
    side: Signal
    signal_date: date


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: Signal
    signal_date: date
    fill_date: date
    quantity: int
    price: Decimal
    notional: Decimal
    fee: Decimal
    realized_pnl: Decimal | None  # sells only


@dataclass(frozen=True)
class Rejection:
    symbol: str
    side: Signal
    signal_date: date
    fill_date: date
    reason: str


@dataclass(frozen=True)
class Holding:
    quantity: int
    cost: Decimal  # buy notional + buy fee


@dataclass(frozen=True)
class EquityPoint:
    date: date
    cash: Decimal
    positions_value: Decimal
    equity: Decimal


@dataclass(frozen=True)
class Account:
    cash: Decimal
    holdings: Mapping[str, Holding] = field(default_factory=dict)
    fills: tuple[Fill, ...] = ()
    rejections: tuple[Rejection, ...] = ()


@dataclass(frozen=True)
class Simulation:
    equity_curve: tuple[EquityPoint, ...]
    account: Account


def simulate(
    calendar: Sequence[date],
    bars: Mapping[str, Sequence[Bar]],
    signals: Mapping[str, Sequence[Signal | None]],
    starting_cash: Decimal,
    costs: Costs,
    position_fraction: Decimal,
) -> Simulation:
    """Run the timeline above. `bars[s][i]` and `signals[s][i]` belong to `calendar[i]` for every symbol."""
    symbols = sorted(bars)
    account = Account(cash=starting_cash)
    curve: list[EquityPoint] = []
    pending: tuple[Order, ...] = ()
    for i, day in enumerate(calendar):
        if pending:
            budget = curve[-1].equity * position_fraction / len(symbols)
            account = _execute(account, pending, {s: bars[s][i] for s in symbols}, costs, budget)
        curve.append(_mark(day, account, {s: bars[s][i].close for s in symbols}))
        is_last = i == len(calendar) - 1
        pending = () if is_last else _orders(day, symbols, {s: signals[s][i] for s in symbols}, account)
    return Simulation(tuple(curve), account)


def _orders(
    day: date, symbols: Sequence[str], today: Mapping[str, Signal | None], account: Account
) -> tuple[Order, ...]:
    def actionable(symbol: str) -> bool:
        held = symbol in account.holdings
        return (today[symbol] == "buy" and not held) or (today[symbol] == "sell" and held)

    return tuple(Order(s, side, day) for s in symbols if (side := today[s]) is not None and actionable(s))


def _execute(
    account: Account, orders: Sequence[Order], bars: Mapping[str, Bar], costs: Costs, budget: Decimal
) -> Account:
    for order in sorted(orders, key=lambda o: (o.side != "sell", o.symbol)):
        bar = bars[order.symbol]
        if order.side == "sell":
            account = _sell(account, order, bar, costs)
        else:
            account = _buy(account, order, bar, costs, budget)
    return account


def _buy(account: Account, order: Order, bar: Bar, costs: Costs, budget: Decimal) -> Account:
    price = min((bar.open * (ONE + costs.slippage)).quantize(PRICE_TICK, ROUND_CEILING), bar.high)
    available = min(budget, account.cash)
    quantity = _affordable(price, available, costs)
    if quantity == 0:
        reason = f"Insufficient cash: {to_cents(available)} does not cover one share at {price} plus fees."
        return _reject(account, order, bar.date, reason)
    notional = to_cents(quantity * price)
    fee = costs.fee(notional)
    fill = Fill(order.symbol, "buy", order.signal_date, bar.date, quantity, price, notional, fee, None)
    return replace(
        account,
        cash=account.cash - notional - fee,
        holdings={**account.holdings, order.symbol: Holding(quantity, notional + fee)},
        fills=(*account.fills, fill),
    )


def _affordable(price: Decimal, available: Decimal, costs: Costs) -> int:
    """The largest whole quantity whose notional + fee is at most `available`."""
    if available <= costs.fee_per_trade:
        return 0
    quantity = int((available - costs.fee_per_trade) / (price * (ONE + costs.fee_rate)))
    while quantity > 0 and to_cents(quantity * price) + costs.fee(to_cents(quantity * price)) > available:
        quantity -= 1  # rounding to cents can push the first estimate one share over
    return quantity


def _sell(account: Account, order: Order, bar: Bar, costs: Costs) -> Account:
    holding = account.holdings[order.symbol]
    price = max((bar.open * (ONE - costs.slippage)).quantize(PRICE_TICK, ROUND_FLOOR), bar.low)
    notional = to_cents(holding.quantity * price)
    fee = costs.fee(notional)
    if account.cash + notional - fee < 0:
        reason = f"The fee {fee} exceeds the sale proceeds {notional} plus cash {account.cash}."
        return _reject(account, order, bar.date, reason)
    realized = notional - fee - holding.cost
    fill = Fill(order.symbol, "sell", order.signal_date, bar.date, holding.quantity, price, notional, fee, realized)
    return replace(
        account,
        cash=account.cash + notional - fee,
        holdings={s: h for s, h in account.holdings.items() if s != order.symbol},
        fills=(*account.fills, fill),
    )


def _reject(account: Account, order: Order, fill_date: date, reason: str) -> Account:
    rejection = Rejection(order.symbol, order.side, order.signal_date, fill_date, reason)
    return replace(account, rejections=(*account.rejections, rejection))


def _mark(day: date, account: Account, closes: Mapping[str, Decimal]) -> EquityPoint:
    positions_value = sum((to_cents(h.quantity * closes[s]) for s, h in account.holdings.items()), ZERO_CASH)
    return EquityPoint(day, account.cash, positions_value, account.cash + positions_value)

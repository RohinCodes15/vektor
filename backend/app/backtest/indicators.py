"""Causal price indicators. Pure: no I/O, Decimal only.

The value at index i uses only values[0..i], so an indicator never sees a later bar. Indexes without enough
history are None.
- SMA(n) at i: mean of values[i - n + 1 .. i]; first defined at i = n - 1.
- RSI(n), Wilder: changes c_k = values[k] - values[k - 1]. The first average gain and loss are the simple means of
  the gains max(c, 0) and losses max(-c, 0) over k = 1..n; later ones are (previous * (n - 1) + current) / n.
  RSI = 100 - 100 / (1 + average gain / average loss); 100 when the average loss is zero, and undefined (None)
  when both averages are zero (no movement). First defined at i = n.
"""

from collections.abc import Sequence
from decimal import Decimal

ZERO = Decimal(0)
HUNDRED = Decimal(100)


def sma(values: Sequence[Decimal], window: int) -> tuple[Decimal | None, ...]:
    if window < 1:
        raise ValueError("window must be at least 1")
    result: list[Decimal | None] = []
    total = ZERO
    for i, value in enumerate(values):
        total += value
        if i >= window:
            total -= values[i - window]
        result.append(total / window if i >= window - 1 else None)
    return tuple(result)


def rsi(values: Sequence[Decimal], period: int) -> tuple[Decimal | None, ...]:
    if period < 1:
        raise ValueError("period must be at least 1")
    result: list[Decimal | None] = [None] * min(len(values), period)
    if len(values) <= period:
        return tuple(result)
    changes = [values[k] - values[k - 1] for k in range(1, len(values))]
    average_gain = sum((max(c, ZERO) for c in changes[:period]), ZERO) / period
    average_loss = sum((max(-c, ZERO) for c in changes[:period]), ZERO) / period
    result.append(_rsi(average_gain, average_loss))
    for change in changes[period:]:
        average_gain = (average_gain * (period - 1) + max(change, ZERO)) / period
        average_loss = (average_loss * (period - 1) + max(-change, ZERO)) / period
        result.append(_rsi(average_gain, average_loss))
    return tuple(result)


def _rsi(average_gain: Decimal, average_loss: Decimal) -> Decimal | None:
    if average_loss == 0:
        return HUNDRED if average_gain > 0 else None
    return HUNDRED - HUNDRED / (1 + average_gain / average_loss)

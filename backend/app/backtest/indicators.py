"""Causal price indicators. Pure: no I/O, Decimal only.

The value at index i uses only values[0..i], so an indicator never sees a later bar. Indexes without enough
history are None.
- SMA(n) at i: mean of values[i - n + 1 .. i]; first defined at i = n - 1.
"""

from collections.abc import Sequence
from decimal import Decimal

ZERO = Decimal(0)


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

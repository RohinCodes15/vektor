"""Current allocation and concentration from a valuation. Pure: no I/O, Decimal only.

Formulas (also in backend/README.md):
- weight_pct: market value / equity * 100, where equity = cash + positions value. Cash is an asset with its own weight.
- position_weight_pct: market value / positions value * 100 (cash excluded), the share of the invested amount.
- Top holding: the largest position_weight_pct (ties: alphabetical symbol).
- HHI: sum of squared position weights as fractions (cash excluded), from 1/N (equal weights) to 1 (one position).
- Rounded to 4 decimal places, ROUND_HALF_EVEN. Unrounded weights feed the HHI.
Nothing is computed from a partial valuation: one unpriced holding makes every weight unknown.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

METRIC_TICK = Decimal("0.0001")


@dataclass(frozen=True)
class Concentration:
    position_weights: dict[str, Decimal]  # fractions of positions value, unrounded
    top_symbol: str
    hhi: Decimal


def concentration(market_values: dict[str, Decimal]) -> Concentration | None:
    """Concentration of priced positions; None when there are no positions or they are worth nothing."""
    total = sum(market_values.values(), Decimal(0))
    if total <= 0:
        return None
    weights = {symbol: value / total for symbol, value in market_values.items()}
    top = min(weights, key=lambda symbol: (-weights[symbol], symbol))
    return Concentration(weights, top, sum((w * w for w in weights.values()), Decimal(0)))


def pct(fraction: Decimal) -> Decimal:
    return rounded(fraction * 100)


def rounded(value: Decimal) -> Decimal:
    return value.quantize(METRIC_TICK, ROUND_HALF_EVEN)

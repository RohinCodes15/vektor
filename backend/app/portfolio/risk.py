"""Volatility contribution and correlation from aligned daily returns. Pure: no I/O, Decimal only.

Formulas (also in backend/README.md):
- Aligned dates: the trading days on which every held symbol has a bar. A return is adjusted_close on one aligned
  date / adjusted_close on the previous aligned date - 1, so every symbol's returns cover the same intervals.
- Covariance: sample covariance (n - 1) of aligned daily returns.
- Weights w: current market value / equity. Cash is in equity with zero return variance, so it dilutes volatility.
- Portfolio volatility: sqrt(w' S w) * sqrt(252), annualized.
- Contribution of asset i: w_i * (S w)_i / sqrt(w' S w) * sqrt(252). Contributions sum to portfolio volatility;
  each share is contribution / portfolio volatility * 100 and the shares sum to 100.
- Correlation: cov(i, j) / (sd_i * sd_j); undefined (None) when either return series is constant.
Assumes current holdings were held over the whole window; past trades are not replayed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import combinations, pairwise

TRADING_DAYS_PER_YEAR = 252
ANNUALIZER = Decimal(TRADING_DAYS_PER_YEAR).sqrt()
ONE = Decimal(1)


@dataclass(frozen=True)
class AlignedReturns:
    dates: tuple[date, ...]  # aligned closing dates; each return ends on dates[k + 1]
    returns: dict[str, tuple[Decimal, ...]]

    @property
    def observations(self) -> int:
        return max(len(self.dates) - 1, 0)


@dataclass(frozen=True)
class AssetMetrics:
    symbol: str
    volatility: Decimal  # annualized fraction
    contribution: Decimal | None  # annualized fraction of portfolio volatility; None when that volatility is zero
    contribution_share: Decimal | None  # fraction of portfolio volatility


@dataclass(frozen=True)
class RiskResult:
    portfolio_volatility: Decimal  # annualized fraction
    assets: tuple[AssetMetrics, ...]
    correlations: tuple[tuple[str, str, Decimal | None], ...]


def align(closes: dict[str, dict[date, Decimal]]) -> AlignedReturns:
    """Returns on the dates every symbol has a close. Missing days are dropped for all symbols, never filled."""
    common = set.intersection(*(set(series) for series in closes.values())) if closes else set()
    dates = tuple(sorted(common))
    returns = {
        symbol: tuple(series[today] / series[previous] - ONE for previous, today in pairwise(dates))
        for symbol, series in closes.items()
    }
    return AlignedReturns(dates, returns)


def compute_risk(weights: dict[str, Decimal], aligned: AlignedReturns) -> RiskResult:
    """`weights` are fractions of equity per symbol; `aligned` must hold at least 2 returns for each symbol."""
    symbols = sorted(weights)
    cov = {(a, b): _covariance(aligned.returns[a], aligned.returns[b]) for a in symbols for b in symbols}
    marginal = {a: sum((cov[a, b] * weights[b] for b in symbols), Decimal(0)) for a in symbols}
    variance = sum((weights[a] * marginal[a] for a in symbols), Decimal(0))
    sd = max(variance, Decimal(0)).sqrt()  # max() absorbs a tiny negative from rounding
    assets = tuple(
        AssetMetrics(
            symbol=a,
            volatility=cov[a, a].sqrt() * ANNUALIZER,
            contribution=weights[a] * marginal[a] / sd * ANNUALIZER if sd else None,
            contribution_share=weights[a] * marginal[a] / variance if sd else None,
        )
        for a in symbols
    )
    correlations = tuple((a, b, _correlation(cov, a, b)) for a, b in combinations(symbols, 2))
    return RiskResult(sd * ANNUALIZER, assets, correlations)


def _correlation(cov: dict[tuple[str, str], Decimal], a: str, b: str) -> Decimal | None:
    denominator = (cov[a, a] * cov[b, b]).sqrt()
    # Clamped: rounding in the last digit can push a perfect correlation just past +-1.
    return max(-ONE, min(ONE, cov[a, b] / denominator)) if denominator else None


def _covariance(x: Sequence[Decimal], y: Sequence[Decimal]) -> Decimal:
    mean_x = sum(x, Decimal(0)) / len(x)
    mean_y = sum(y, Decimal(0)) / len(y)
    return sum(((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True)), Decimal(0)) / (len(x) - 1)

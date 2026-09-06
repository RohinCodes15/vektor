from datetime import date
from decimal import Decimal

import pytest

from app.portfolio.risk import ANNUALIZER, align, compute_risk

D = [date(2024, 1, day) for day in range(1, 8)]


def series(*closes: str) -> dict[date, Decimal]:
    return {day: Decimal(close) for day, close in zip(D, closes, strict=False)}


def test_align_keeps_only_dates_every_symbol_has() -> None:
    a = series("100", "110", "121", "133.1")
    b = {day: close for day, close in series("10", "11", "12", "13").items() if day != D[1]}
    aligned = align({"A": a, "B": b})
    assert aligned.dates == (D[0], D[2], D[3])
    assert aligned.observations == 2
    assert aligned.returns["A"] == (Decimal("0.21"), Decimal("0.1"))  # 121/100 - 1 spans the dropped day
    assert aligned.returns["B"][0] == Decimal("0.2")


def test_align_with_no_common_dates_has_no_returns() -> None:
    aligned = align({"A": {D[0]: Decimal(1)}, "B": {D[1]: Decimal(1)}})
    assert aligned.dates == () and aligned.observations == 0


def test_single_asset_carries_all_risk_scaled_by_its_weight() -> None:
    aligned = align({"A": series("100", "102", "99", "103", "101")})
    result = compute_risk({"A": Decimal("0.5")}, aligned)
    (asset,) = result.assets
    assert result.portfolio_volatility == pytest.approx(asset.volatility / 2, rel=Decimal("1e-20"))
    assert asset.contribution == pytest.approx(result.portfolio_volatility, rel=Decimal("1e-20"))
    assert asset.contribution_share == 1
    assert result.correlations == ()


def test_contributions_sum_to_portfolio_volatility() -> None:
    aligned = align({"A": series("100", "102", "99", "103", "101"), "B": series("50", "49", "51", "50", "52")})
    weights = {"A": Decimal("0.4"), "B": Decimal("0.3")}
    result = compute_risk(weights, aligned)
    contributions = sum(a.contribution for a in result.assets if a.contribution is not None)
    shares = sum(a.contribution_share for a in result.assets if a.contribution_share is not None)
    assert contributions == pytest.approx(result.portfolio_volatility, rel=Decimal("1e-20"))
    assert shares == pytest.approx(Decimal(1), rel=Decimal("1e-20"))


def test_known_two_asset_volatility() -> None:
    # Returns A: +10%, -10%; B: -10%, +10%. Equal weights cancel exactly.
    aligned = align({"A": series("100", "110", "99"), "B": series("100", "90", "99")})
    result = compute_risk({"A": Decimal("0.5"), "B": Decimal("0.5")}, aligned)
    assert result.correlations == (("A", "B", Decimal(-1)),)
    assert result.portfolio_volatility == 0
    assert all(a.contribution is None and a.contribution_share is None for a in result.assets)
    # A's sample sd of (+0.1, -0.1) is sqrt(0.02).
    assert result.assets[0].volatility == pytest.approx(Decimal("0.02").sqrt() * ANNUALIZER)


def test_perfectly_correlated_and_constant_series() -> None:
    aligned = align({
        "A": series("100", "110", "99", "120"),
        "B": series("10", "11", "9.9", "12"),
        "C": series("5", "5", "5", "5"),
    })
    result = compute_risk({"A": Decimal("0.3"), "B": Decimal("0.3"), "C": Decimal("0.4")}, aligned)
    correlations = {(a, b): c for a, b, c in result.correlations}
    assert correlations["A", "B"] == pytest.approx(Decimal(1))
    assert correlations["A", "C"] is None and correlations["B", "C"] is None
    assert next(a for a in result.assets if a.symbol == "C").contribution == 0

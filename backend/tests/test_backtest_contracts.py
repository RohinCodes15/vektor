from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts import BacktestCreate, BuyAndHoldStrategy, RsiStrategy, SmaCrossoverStrategy

YESTERDAY = datetime.now(UTC).date() - timedelta(days=1)


def request(**overrides: Any) -> BacktestCreate:
    body: dict[str, Any] = {
        "symbols": ["aapl"], "start": "2024-01-01", "end": "2024-06-28", "starting_cash": "10000",
        "strategy": {"kind": "buy_and_hold"}, **overrides,
    }
    return BacktestCreate.model_validate(body)


def test_defaults_are_frictionless_and_fully_invested() -> None:
    parsed = request()
    assert parsed.symbols == ["AAPL"]
    assert parsed.starting_cash == Decimal("10000.00")
    assert isinstance(parsed.strategy, BuyAndHoldStrategy)
    assert (parsed.position_size_pct, parsed.fee_per_trade, parsed.fee_bps, parsed.slippage_bps) == (
        Decimal(100), Decimal("0.00"), Decimal(0), Decimal(0),
    )


def test_strategy_is_chosen_by_kind_with_parameter_defaults() -> None:
    sma = request(strategy={"kind": "sma_crossover"}).strategy
    assert isinstance(sma, SmaCrossoverStrategy) and (sma.fast_window, sma.slow_window) == (20, 50)
    rsi = request(strategy={"kind": "rsi", "period": 7, "oversold": "25.5"}).strategy
    assert isinstance(rsi, RsiStrategy) and (rsi.period, rsi.oversold, rsi.overbought) == (7, Decimal("25.5"), 70)


def test_costs_are_canonical_in_the_json_contract() -> None:
    parsed = request(fee_per_trade="1.5", fee_bps="2.50", slippage_bps="5", position_size_pct="50.0")
    dumped = parsed.model_dump(mode="json")
    assert (dumped["fee_per_trade"], dumped["fee_bps"], dumped["slippage_bps"], dumped["position_size_pct"]) == (
        "1.50", "2.5", "5", "50",
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"symbols": []}, "at least 1"),
        ({"symbols": ["AAPL", "aapl"]}, "must not repeat"),
        ({"symbols": [{"ticker": "AAPL"}]}, "valid string"),
        ({"symbols": [["AAPL"], ["AAPL"]]}, "valid string"),
        ({"symbols": ["^GSPC"]}, "ticker"),
        ({"symbols": [f"S{i}" for i in range(11)]}, "at most 10"),
        ({"start": "2024-06-28"}, "start must be before end"),
        ({"end": YESTERDAY.isoformat(), "start": (YESTERDAY + timedelta(days=-5)).isoformat()}, None),
        ({"end": (YESTERDAY + timedelta(days=1)).isoformat()}, "before today"),
        ({"starting_cash": "0"}, "greater than 0"),
        ({"starting_cash": "10.001"}, "decimal places"),
        ({"position_size_pct": "0"}, "greater than 0"),
        ({"position_size_pct": "100.01"}, "less than or equal to 100"),
        ({"fee_per_trade": "-1"}, "greater than or equal to 0"),
        ({"fee_bps": "1000.01"}, "less than or equal to 1000"),
        ({"slippage_bps": "-0.01"}, "greater than or equal to 0"),
        ({"strategy": {"kind": "momentum"}}, "does not match any of the expected tags"),
        ({"strategy": {"kind": "sma_crossover", "fast_window": 50, "slow_window": 50}}, "fast_window must be smaller"),
        ({"strategy": {"kind": "sma_crossover", "fast_window": 1}}, "greater than or equal to 2"),
        ({"strategy": {"kind": "rsi", "oversold": 70, "overbought": 30}}, "oversold must be below overbought"),
        ({"strategy": {"kind": "rsi", "period": 1}}, "greater than or equal to 2"),
        ({"strategy": {"kind": "buy_and_hold", "window": 3}}, "Extra inputs are not permitted"),
        ({"broker": "alpaca"}, "Extra inputs are not permitted"),
    ],
)
def test_invalid_requests_are_rejected(overrides: dict[str, Any], message: str | None) -> None:
    if message is None:  # control: yesterday is the latest allowed end
        assert request(**overrides).end == YESTERDAY
        return
    with pytest.raises(ValidationError, match=message):
        request(**overrides)

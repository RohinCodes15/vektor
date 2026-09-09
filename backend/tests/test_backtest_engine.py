import random
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.backtest.engine import Costs, Holding, Simulation, _affordable, simulate
from app.backtest.prices import Bar
from app.backtest.strategies import Signal, signal_series
from app.contracts import RsiStrategy, SmaCrossoverStrategy

D = Decimal
FREE = Costs(fee_per_trade=D("0.00"), fee_rate=D(0), slippage=D(0))
START = date(2024, 1, 1)


def calendar(n: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n)]


def bars(*ohlc: tuple[float, float, float, float]) -> list[Bar]:
    return [Bar(day, *(D(str(v)) for v in prices)) for day, prices in zip(calendar(len(ohlc)), ohlc, strict=True)]


def flat(*closes: float) -> list[Bar]:
    return bars(*((c, c, c, c) for c in closes))


def run(
    series: dict[str, list[Bar]],
    signals: dict[str, Sequence[Signal | None]],
    cash: str = "1000.00",
    costs: Costs = FREE,
    fraction: str = "1",
) -> Simulation:
    days = calendar(len(next(iter(series.values()))))
    return simulate(days, series, signals, D(cash), costs, D(fraction))


TREND = bars((10, 11, 9, 10), (12, 13, 11, 12), (14, 15, 13, 15))


def test_a_signal_fills_at_the_next_bars_open_never_its_own_close() -> None:
    result = run({"A": TREND}, {"A": ["buy", None, None]})
    (fill,) = result.account.fills
    assert (fill.signal_date, fill.fill_date) == (START, START + timedelta(days=1))
    assert (fill.price, fill.quantity, fill.notional, fill.fee) == (D(12), 83, D("996.00"), D("0.00"))
    assert [p.equity for p in result.equity_curve] == [D("1000.00"), D("1000.00"), D("1249.00")]
    assert [p.cash for p in result.equity_curve] == [D("1000.00"), D("4.00"), D("4.00")]
    assert result.account.holdings == {"A": Holding(83, D("996.00"))}


def test_a_signal_on_the_last_bar_never_fills() -> None:
    result = run({"A": TREND}, {"A": [None, None, "buy"]})
    assert result.account.fills == () and result.account.rejections == ()
    assert [p.equity for p in result.equity_curve] == [D("1000.00")] * 3


def test_round_trip_realizes_pnl_after_fees_on_both_legs() -> None:
    costs = Costs(fee_per_trade=D("1.00"), fee_rate=D("0.001"), slippage=D(0))
    prices = bars((10, 10, 10, 10), (12, 12, 12, 12), (14, 14, 14, 14))
    result = run({"A": prices}, {"A": ["buy", "sell", None]}, costs=costs)
    buy, sell = result.account.fills
    # Buy 83 at 12: notional 996.00, fee 1 + 0.996 = 2.00 (cents). Sell at 14: 1162.00, fee 1 + 1.162 = 2.16.
    assert (buy.quantity, buy.notional, buy.fee, buy.realized_pnl) == (83, D("996.00"), D("2.00"), None)
    assert (sell.quantity, sell.notional, sell.fee) == (83, D("1162.00"), D("2.16"))
    assert sell.realized_pnl == D("1162.00") - D("2.16") - D("998.00")
    assert result.account.cash == D("1161.84") and result.account.holdings == {}
    assert result.equity_curve[-1].equity == D("1161.84")


def test_slippage_moves_fills_against_the_trader() -> None:
    costs = Costs(fee_per_trade=D("0.00"), fee_rate=D(0), slippage=D("0.01"))
    prices = bars((10, 10, 10, 10), (12, 13, 11, 12), (14, 15, 13, 14))
    buy, sell = run({"A": prices}, {"A": ["buy", "sell", None]}, costs=costs).account.fills
    assert (buy.price, sell.price) == (D("12.12"), D("13.86"))


def test_slipped_prices_round_against_the_trader() -> None:
    costs = Costs(fee_per_trade=D("0.00"), fee_rate=D(0), slippage=D("0.0001"))
    prices = bars((10, 10, 10, 10), (10.0001, 11, 9, 10), (10.0001, 11, 9, 10))
    buy, sell = run({"A": prices}, {"A": ["buy", "sell", None]}, costs=costs).account.fills
    assert (buy.price, sell.price) == (D("10.0012"), D("9.9990"))  # 10.00110001 up, 9.99909999 down


def test_fills_never_leave_the_bars_traded_range() -> None:
    costs = Costs(fee_per_trade=D("0.00"), fee_rate=D(0), slippage=D("0.10"))
    prices = bars((10, 10, 10, 10), (12, 12.5, 11, 12), (14, 15, 13.5, 14))
    buy, sell = run({"A": prices}, {"A": ["buy", "sell", None]}, costs=costs).account.fills
    assert buy.price == D("12.5")  # 13.2 capped at the high
    assert sell.price == D("13.5")  # 12.6 floored at the low


def test_a_buy_that_cannot_afford_one_share_is_rejected_and_changes_nothing() -> None:
    costs = Costs(fee_per_trade=D("5.00"), fee_rate=D(0), slippage=D(0))
    result = run({"A": TREND}, {"A": ["buy", None, None]}, cash="10.00", costs=costs)
    assert result.account.fills == ()
    (rejection,) = result.account.rejections
    assert (rejection.side, rejection.signal_date, rejection.fill_date) == ("buy", START, START + timedelta(days=1))
    assert "Insufficient cash" in rejection.reason
    assert [p.equity for p in result.equity_curve] == [D("10.00")] * 3


def test_a_sell_whose_fee_exceeds_proceeds_plus_cash_is_rejected() -> None:
    costs = Costs(fee_per_trade=D("5.00"), fee_rate=D(0), slippage=D(0))
    prices = bars((10, 10, 10, 10), (10, 10, 10, 10), (0.4, 0.5, 0.3, 0.4))
    result = run({"A": prices}, {"A": ["buy", "sell", None]}, cash="105.00", costs=costs)
    (buy,) = result.account.fills
    assert (buy.quantity, result.account.cash) == (10, D("0.00"))
    (rejection,) = result.account.rejections
    assert rejection.side == "sell" and "exceeds the sale proceeds" in rejection.reason
    assert result.account.holdings == {"A": Holding(10, D("105.00"))}  # still held; cash never negative


def test_buys_target_equal_slices_of_equity_within_available_cash() -> None:
    result = run({"A": flat(10, 10, 10), "B": flat(30, 30, 30)}, {"A": ["buy", None, None], "B": ["buy", None, None]})
    a, b = result.account.fills
    assert (a.symbol, a.quantity, b.symbol, b.quantity) == ("A", 50, "B", 16)  # 500 each: 50 x 10, 16 x 30
    assert result.account.cash == D("20.00")


def test_position_size_limits_the_amount_invested() -> None:
    (fill,) = run({"A": flat(10, 10, 10)}, {"A": ["buy", None, None]}, fraction="0.25").account.fills
    assert fill.quantity == 25


def test_sells_fill_before_buys_so_their_proceeds_can_be_spent() -> None:
    series = {"A": flat(10, 10, 30, 30), "B": flat(10, 10, 10, 10)}
    signals: dict[str, Sequence[Signal | None]] = {"A": ["buy", None, "sell", None], "B": [None, None, "buy", None]}
    result = run(series, signals)
    sides = [(f.symbol, f.side, f.quantity) for f in result.account.fills]
    # Bar 3: equity at bar 2 is 2000, so B targets 1000. Without A's proceeds only 500 cash would be on hand.
    assert sides == [("A", "buy", 50), ("A", "sell", 50), ("B", "buy", 100)]


def test_redundant_signals_are_ignored() -> None:
    result = run({"A": flat(10, 10, 10, 10, 10)}, {"A": ["sell", "buy", "buy", "sell", "sell"]})
    assert [(f.side, f.fill_date) for f in result.account.fills] == [
        ("buy", START + timedelta(days=2)), ("sell", START + timedelta(days=4)),
    ]
    assert result.account.rejections == ()


def test_affordable_steps_back_when_the_rounded_fee_overshoots() -> None:
    costs = Costs(fee_per_trade=D("0.00"), fee_rate=D("0.0046"), slippage=D(0))
    # 10 shares cost exactly 10.046, but the fee rounds up to 0.05, so only 9 fit.
    assert _affordable(D(1), D("10.046"), costs) == 9
    assert _affordable(D(1), D("10.05"), costs) == 10
    assert _affordable(D(1), D("0.00"), costs) == 0


def random_market(seed: int, n: int = 120) -> list[Bar]:
    rng = random.Random(seed)
    price = 50.0
    rows = []
    for _ in range(n):
        open_ = price * rng.uniform(0.97, 1.03)
        close = open_ * rng.uniform(0.95, 1.05)
        rows.append((round(open_, 2), round(max(open_, close) * 1.01, 2), round(min(open_, close) * 0.99, 2),
                     round(close, 2)))
        price = close
    return bars(*rows)


@pytest.mark.parametrize("seed", range(5))
def test_invariants_hold_on_random_markets(seed: int) -> None:
    rng = random.Random(seed)
    series = {"A": random_market(seed), "B": random_market(seed + 100)}
    signals = {s: [rng.choice(["buy", "sell", None]) for _ in range(120)] for s in series}
    costs = Costs(fee_per_trade=D("1.00"), fee_rate=D("0.0005"), slippage=D("0.002"))
    result = run(series, signals, cash="5000.00", costs=costs)  # type: ignore[arg-type]
    by_day = {s: {b.date: b for b in bs} for s, bs in series.items()}
    assert result.account.fills
    for fill in result.account.fills:
        bar = by_day[fill.symbol][fill.fill_date]
        assert bar.low <= fill.price <= bar.high
        assert fill.fill_date > fill.signal_date
        assert fill.quantity > 0
    assert all(p.cash >= 0 and p.equity == p.cash + p.positions_value for p in result.equity_curve)
    assert run(series, signals, cash="5000.00", costs=costs) == result  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "strategy",
    [SmaCrossoverStrategy(kind="sma_crossover", fast_window=3, slow_window=8), RsiStrategy(kind="rsi", period=5)],
)
def test_results_up_to_a_bar_never_depend_on_later_bars(strategy: SmaCrossoverStrategy | RsiStrategy) -> None:
    market = random_market(7)
    costs = Costs(fee_per_trade=D("1.00"), fee_rate=D("0.001"), slippage=D("0.001"))

    def backtest(prefix: list[Bar]) -> Simulation:
        signals = {"A": signal_series(strategy, [b.close for b in prefix])}
        return run({"A": prefix}, signals, costs=costs)

    full = backtest(market)
    assert full.account.fills
    for end in range(10, len(market), 7):
        partial = backtest(market[: end + 1])
        assert partial.equity_curve == full.equity_curve[: end + 1]
        assert partial.account.fills == tuple(f for f in full.account.fills if f.fill_date <= market[end].date)

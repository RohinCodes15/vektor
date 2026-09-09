from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from app.backtest.engine import Costs, Holding, Simulation, simulate
from app.backtest.prices import Bar
from app.backtest.strategies import Signal

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

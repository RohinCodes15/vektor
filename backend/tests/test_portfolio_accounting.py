from datetime import date
from decimal import Decimal

import pytest

from app.portfolio.accounting import (
    Position,
    Quote,
    fill_order,
    to_cents,
    to_percent,
    to_price,
    value_portfolio,
)
from app.portfolio.errors import OrderRejected

D = Decimal


def quote(price: str) -> Quote:
    return Quote(D(price), date(2024, 1, 5))


@pytest.mark.parametrize(
    ("amount", "expected"),
    [("0.005", "0.00"), ("0.015", "0.02"), ("0.025", "0.02"), ("1.234", "1.23"), ("-0.015", "-0.02"), ("7", "7.00")],
)
def test_money_rounds_half_even_to_cents(amount: str, expected: str) -> None:
    assert str(to_cents(D(amount))) == expected


@pytest.mark.parametrize(
    ("close", "expected"),
    [(185.63999938964844, "185.6400"), (0.12345, "0.1234"), (0.12355, "0.1236"), (100.0, "100.0000"), (3, "3.0000")],
)
def test_prices_round_half_even_to_four_places(close: float, expected: str) -> None:
    assert str(to_price(close)) == expected


def test_percentages_round_to_two_places_and_are_undefined_for_zero_equity() -> None:
    assert to_percent(D("1"), D("3")) == D("33.33")
    assert to_percent(D("2"), D("3")) == D("66.67")
    assert to_percent(D("1"), D("0")) is None


def test_buy_spends_the_rounded_notional_and_opens_a_position() -> None:
    fill = fill_order("buy", "AAPL", D("3"), D("33.3333"), D("1000.00"), None)
    assert fill.notional == D("100.00")  # 99.9999 rounds to cents
    assert fill.cash == D("900.00")
    assert fill.position == Position("AAPL", D("3"), D("100.00"))
    assert fill.realized_pnl is None


def test_buy_adds_to_an_existing_position_at_average_cost() -> None:
    held = Position("AAPL", D("10"), D("1000.00"))
    fill = fill_order("buy", "AAPL", D("5"), D("130"), D("2000.00"), held)
    assert fill.position == Position("AAPL", D("15"), D("1650.00"))
    assert fill.cash == D("1350.00")


def test_buy_may_spend_exactly_all_cash() -> None:
    fill = fill_order("buy", "AAPL", D("10"), D("100"), D("1000.00"), None)
    assert fill.cash == D("0.00")


def test_buy_with_insufficient_cash_is_rejected() -> None:
    with pytest.raises(OrderRejected) as error:
        fill_order("buy", "AAPL", D("10"), D("100.01"), D("1000.00"), None)
    assert error.value.message == (
        "Insufficient cash: buying 10 AAPL at 100.01 costs 1000.10, available cash is 1000.00."
    )


def test_buy_worth_less_than_a_cent_is_rejected() -> None:
    with pytest.raises(OrderRejected, match="rounds to \\$0.00"):
        fill_order("buy", "PENNY", D("0.000001"), D("0.5000"), D("1000.00"), None)


def test_partial_sell_realizes_pnl_against_average_cost() -> None:
    held = Position("AAPL", D("3"), D("100.00"))
    fill = fill_order("sell", "AAPL", D("1"), D("40"), D("0.00"), held)
    # Sold basis 100.00 * 1/3 = 33.33; remaining 66.67.
    assert fill.notional == D("40.00")
    assert fill.realized_pnl == D("6.67")
    assert fill.position == Position("AAPL", D("2"), D("66.67"))
    assert fill.cash == D("40.00")


def test_full_sell_removes_the_whole_basis_and_closes_the_position() -> None:
    held = Position("AAPL", D("2"), D("66.67"))
    fill = fill_order("sell", "AAPL", D("2"), D("30"), D("40.00"), held)
    assert fill.position is None
    assert fill.realized_pnl == D("-6.67")
    assert fill.cash == D("100.00")


def test_selling_more_than_held_is_rejected() -> None:
    with pytest.raises(OrderRejected) as error:
        fill_order("sell", "AAPL", D("5.5"), D("100"), D("0.00"), Position("AAPL", D("5"), D("500.00")))
    assert error.value.message == "Cannot sell 5.5 AAPL: the portfolio holds 5."


def test_selling_a_symbol_not_held_is_rejected() -> None:
    with pytest.raises(OrderRejected, match="holds none. Short selling is not supported"):
        fill_order("sell", "AAPL", D("1"), D("100"), D("1000.00"), None)


def test_fractional_quantities_are_exact() -> None:
    held = Position("BTC-USD", D("0.3"), D("30.00"))
    fill = fill_order("sell", "BTC-USD", D("0.1"), D("100"), D("0.00"), held)
    assert fill.position == Position("BTC-USD", D("0.2"), D("20.00"))
    assert fill.realized_pnl == D("0.00")


def test_valuation_computes_equity_pnl_and_allocation() -> None:
    positions = [Position("AAPL", D("10"), D("1000.00")), Position("MSFT", D("2"), D("500.00"))]
    result = value_portfolio(D("500.00"), positions, {"AAPL": quote("120"), "MSFT": quote("200")})
    assert result.positions_value == D("1600.00")
    assert result.equity == D("2100.00")
    assert result.unrealized_pnl == D("100.00")
    assert result.cash_allocation_pct == D("23.81")
    aapl, msft = result.holdings
    assert (aapl.market_value, aapl.unrealized_pnl, aapl.allocation_pct) == (D("1200.00"), D("200.00"), D("57.14"))
    assert (msft.market_value, msft.unrealized_pnl, msft.allocation_pct) == (D("400.00"), D("-100.00"), D("19.05"))
    assert (aapl.last_price, aapl.price_date) == (D("120"), date(2024, 1, 5))


def test_valuation_with_only_cash() -> None:
    result = value_portfolio(D("1000.00"), [], {})
    assert (result.positions_value, result.equity, result.unrealized_pnl) == (D("0.00"), D("1000.00"), D("0.00"))
    assert result.cash_allocation_pct == D("100.00") and result.holdings == ()


def test_valuation_never_guesses_a_missing_price() -> None:
    positions = [Position("AAPL", D("10"), D("1000.00")), Position("GONE", D("1"), D("50.00"))]
    result = value_portfolio(D("500.00"), positions, {"AAPL": quote("120"), "GONE": None})
    assert (result.positions_value, result.equity, result.unrealized_pnl, result.cash_allocation_pct) == (
        None, None, None, None,
    )
    aapl, gone = result.holdings
    assert (aapl.market_value, aapl.unrealized_pnl, aapl.allocation_pct) == (D("1200.00"), D("200.00"), None)
    assert (gone.last_price, gone.price_date, gone.market_value, gone.unrealized_pnl, gone.allocation_pct) == (
        None, None, None, None, None,
    )
    assert (gone.quantity, gone.cost_basis) == (D("1"), D("50.00"))


def test_valuation_with_zero_equity_has_no_allocation() -> None:
    result = value_portfolio(D("0.00"), [Position("DUST", D("0.000001"), D("0.01"))], {"DUST": quote("1")})
    assert result.equity == D("0.00")
    assert result.cash_allocation_pct is None and result.holdings[0].allocation_pct is None

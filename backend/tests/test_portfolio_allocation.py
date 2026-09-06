from decimal import Decimal

from app.portfolio.allocation import concentration, pct, rounded


def test_no_positions_or_zero_value_has_no_concentration() -> None:
    assert concentration({}) is None
    assert concentration({"AAPL": Decimal("0.00")}) is None


def test_weights_top_holding_and_hhi() -> None:
    result = concentration({"AAPL": Decimal("600.00"), "MSFT": Decimal("300.00"), "KO": Decimal("100.00")})
    assert result is not None
    assert result.position_weights == {"AAPL": Decimal("0.6"), "MSFT": Decimal("0.3"), "KO": Decimal("0.1")}
    assert result.top_symbol == "AAPL"
    assert result.hhi == Decimal("0.46")  # 0.36 + 0.09 + 0.01


def test_single_position_is_fully_concentrated() -> None:
    result = concentration({"AAPL": Decimal("10.00")})
    assert result is not None and result.hhi == 1 and result.top_symbol == "AAPL"


def test_equal_weights_give_hhi_of_one_over_n_and_alphabetical_top() -> None:
    result = concentration({"MSFT": Decimal("50.00"), "AAPL": Decimal("50.00"), "KO": Decimal("50.00")})
    assert result is not None
    assert result.top_symbol == "AAPL"
    assert rounded(result.hhi) == Decimal("0.3333")
    assert pct(result.position_weights["KO"]) == Decimal("33.3333")

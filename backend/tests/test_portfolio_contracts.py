from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts import PaperOrder, PortfolioCreate, PortfolioUpdate


def order(**overrides: object) -> PaperOrder:
    return PaperOrder(**{"client_order_id": "order-1", "symbol": "AAPL", "side": "buy", "quantity": "1", **overrides})


def test_portfolio_create_strips_the_name_and_stores_cash_in_cents() -> None:
    created = PortfolioCreate(name="  Growth  ", starting_cash="1000.5")
    assert created.name == "Growth"
    assert str(created.starting_cash) == "1000.50"


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "", "starting_cash": "100"},
        {"name": "   ", "starting_cash": "100"},
        {"name": "x" * 101, "starting_cash": "100"},
        {"name": "x", "starting_cash": "0"},
        {"name": "x", "starting_cash": "-5"},
        {"name": "x", "starting_cash": "100.001"},
        {"name": "x", "starting_cash": "NaN"},
        {"name": "x", "starting_cash": "Infinity"},
        {"name": "x", "starting_cash": "1000000000000"},  # 13 integer digits exceeds max_digits=14 with 2 places
        {"name": "x", "starting_cash": "100", "cash": "999"},
    ],
)
def test_portfolio_create_rejects_invalid_input(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        PortfolioCreate(**fields)


def test_portfolio_update_only_accepts_a_name() -> None:
    assert PortfolioUpdate(name=" New ").name == "New"
    with pytest.raises(ValidationError):
        PortfolioUpdate(name="x", cash="1000000")


@pytest.mark.parametrize(("raw", "expected"), [("aapl", "AAPL"), (" brk-b ", "BRK-B"), ("BRK.B", "BRK.B"),
                                               ("btc-usd", "BTC-USD")])
def test_order_normalizes_symbols(raw: str, expected: str) -> None:
    assert order(symbol=raw).symbol == expected


@pytest.mark.parametrize("raw", ["", "^GSPC", "GC=F", "EURUSD=X", "AA PL", "A" * 16, "-AAPL", "AAPL;"])
def test_order_rejects_untradable_or_malformed_symbols(raw: str) -> None:
    with pytest.raises(ValidationError, match="symbol must be a ticker"):
        order(symbol=raw)


@pytest.mark.parametrize(("raw", "expected"), [("1.50", "1.5"), ("10", "10"), ("1E+1", "10"), ("0.000001", "0.000001")])
def test_order_quantity_is_canonical(raw: str, expected: str) -> None:
    assert str(order(quantity=raw).quantity) == expected


@pytest.mark.parametrize("quantity", ["0", "-1", "0.0000001", "NaN", "Infinity", "12345678901"])
def test_order_rejects_invalid_quantities(quantity: str) -> None:
    with pytest.raises(ValidationError):
        order(quantity=quantity)


@pytest.mark.parametrize(
    "fields",
    [
        {"side": "short"},
        {"client_order_id": ""},
        {"client_order_id": "x" * 65},
        {"client_order_id": "has space"},
        {"type": "limit"},
        {"limit_price": "10"},
    ],
)
def test_order_rejects_invalid_fields(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        order(**fields)


def test_order_requires_a_client_order_id() -> None:
    with pytest.raises(ValidationError, match="client_order_id"):
        PaperOrder(symbol="AAPL", side="buy", quantity=Decimal(1))

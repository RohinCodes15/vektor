from app.validation import summarize_errors


def test_summarize_errors_joins_locations_and_messages() -> None:
    errors = [
        {"loc": ("query", "symbol"), "msg": "Value error, symbol must be valid", "input": "secret-input"},
        {"loc": ("query",), "msg": "Value error, start must be on or before end"},
        {"loc": ("bars", 0, "open"), "msg": "Input should be greater than 0"},
    ]
    summary = summarize_errors(errors)
    assert summary == "symbol: symbol must be valid; start must be on or before end; bars.0.open: Input should be greater than 0"
    assert "secret-input" not in summary


def test_summarize_errors_has_a_fallback() -> None:
    assert summarize_errors([]) == "Invalid request"
    assert summarize_errors([{}]) == "Invalid value"

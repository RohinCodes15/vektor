import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.analysis.errors import AnalysisUnavailable, InvalidAnalysis
from app.analysis.facts import measured_facts
from app.analysis.prompt import SYSTEM_PROMPT, provider_payload
from app.analysis.service import DISCLAIMER, AnalysisService
from app.backtest.errors import BacktestNotFound
from tests.analysis_support import NOW, SWING, FakeAI, interpretation, run_backtest

SMA = {"kind": "sma_crossover", "fast_window": 2, "slow_window": 3}


def test_without_a_provider_the_analysis_is_unavailable_but_facts_are_exact(tmp_path: Path) -> None:
    backtests, backtest = run_backtest(tmp_path, SWING, SMA)
    result = AnalysisService(backtests, None, clock=lambda: NOW).analyze(backtest.id)
    assert (result.status, result.interpretation, result.provider, result.model) == ("unavailable", None, None, None)
    assert result.unavailable_reason is not None and "VEKTOR_AI_PROVIDER" in result.unavailable_reason
    assert result.facts == list(measured_facts(backtest))
    assert (result.mode, result.generated_at, result.disclaimer) == ("paper", NOW, DISCLAIMER)


def test_the_provider_receives_only_the_measured_facts_and_its_reading_is_returned(tmp_path: Path) -> None:
    backtests, backtest = run_backtest(tmp_path, SWING, SMA)
    ai = FakeAI()
    result = AnalysisService(backtests, ai, clock=lambda: NOW).analyze(backtest.id)
    assert (result.status, result.provider, result.model, result.unavailable_reason) == (
        "available", "anthropic", "test-model", None,
    )
    assert result.interpretation == ai.result
    ((system, payload),) = ai.calls
    assert system == SYSTEM_PROMPT
    sent = json.loads(payload)
    assert sent == {"facts": [f.model_dump() for f in measured_facts(backtest)], "metric_notes": backtest.warnings}


def test_the_payload_holds_no_ids_timestamps_or_account_amounts(tmp_path: Path) -> None:
    _, backtest = run_backtest(tmp_path, SWING, SMA)
    payload = provider_payload(measured_facts(backtest), backtest.warnings)
    for private in [str(backtest.id), backtest.created_at.isoformat(), str(backtest.config.starting_cash),
                    str(backtest.metrics.final_equity)]:
        assert private not in payload
    assert payload == provider_payload(measured_facts(backtest), backtest.warnings)  # deterministic


def test_an_interpretation_citing_unmeasured_facts_is_rejected(tmp_path: Path) -> None:
    backtests, backtest = run_backtest(tmp_path, SWING, SMA)
    ai = FakeAI(interpretation(evidence=["total_return_pct", "next_year_forecast"]))
    with pytest.raises(InvalidAnalysis, match="cites facts that were not measured"):
        AnalysisService(backtests, ai).analyze(backtest.id)


def test_provider_failures_propagate_unchanged(tmp_path: Path) -> None:
    backtests, backtest = run_backtest(tmp_path, SWING, SMA)
    with pytest.raises(AnalysisUnavailable, match="timed out"):
        AnalysisService(backtests, FakeAI(AnalysisUnavailable("The AI provider timed out."))).analyze(backtest.id)


def test_an_unknown_backtest_is_not_found_and_the_provider_is_not_called(tmp_path: Path) -> None:
    backtests, _ = run_backtest(tmp_path, SWING, SMA)
    ai = FakeAI()
    with pytest.raises(BacktestNotFound):
        AnalysisService(backtests, ai).analyze(uuid4())
    assert ai.calls == []

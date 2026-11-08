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

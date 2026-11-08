"""Explain a stored backtest: exact measured facts, plus an AI interpretation when a provider is configured.

The interpretation is grounded: every insight must cite measured fact ids, or the whole reply is rejected (502).
With no provider configured the response says "unavailable" and carries the facts only; nothing is ever fabricated.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from app.analysis.errors import InvalidAnalysis
from app.analysis.facts import measured_facts
from app.analysis.prompt import SYSTEM_PROMPT, provider_payload
from app.analysis.provider import AnalysisProvider
from app.backtest.service import BacktestService
from app.contracts import AnalysisFact, AnalysisInterpretation, BacktestAnalysis
from app.market_data.service import utc_now

logger = logging.getLogger("vektor.analysis")

DISCLAIMER = (
    "Educational analysis of a simulated, paper-only backtest on historical data. Simulated past performance does not "
    "predict future results. This is not investment advice or a recommendation to buy, sell, or hold any security."
)
NOT_CONFIGURED = (
    "AI analysis is not configured: set VEKTOR_AI_PROVIDER to enable it. The measured facts are still exact."
)


class AnalysisService:
    def __init__(
        self,
        backtests: BacktestService,
        provider: AnalysisProvider | None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._backtests = backtests
        self._provider = provider
        self._clock = clock

    def analyze(self, backtest_id: UUID) -> BacktestAnalysis:
        """Raises BacktestNotFound, AnalysisUnavailable (503), or InvalidAnalysis (502)."""
        backtest = self._backtests.get(backtest_id)
        facts = measured_facts(backtest)
        if self._provider is None:
            return self._result(backtest_id, facts, None, NOT_CONFIGURED)
        interpretation = self._provider.interpret(SYSTEM_PROMPT, provider_payload(facts, backtest.warnings))
        check_grounding(interpretation, facts)
        logger.info(
            "backtest analysis generated",
            extra={"backtest_id": str(backtest_id), "provider": self._provider.name, "model": self._provider.model},
        )
        return self._result(backtest_id, facts, interpretation, None)

    def _result(
        self,
        backtest_id: UUID,
        facts: Sequence[AnalysisFact],
        interpretation: AnalysisInterpretation | None,
        unavailable_reason: str | None,
    ) -> BacktestAnalysis:
        provider = self._provider if interpretation is not None else None
        return BacktestAnalysis(
            backtest_id=backtest_id,
            status="available" if interpretation is not None else "unavailable",
            unavailable_reason=unavailable_reason,
            generated_at=self._clock(),
            provider=provider.name if provider else None,
            model=provider.model if provider else None,
            facts=list(facts),
            interpretation=interpretation,
            disclaimer=DISCLAIMER,
        )


def check_grounding(interpretation: AnalysisInterpretation, facts: Sequence[AnalysisFact]) -> None:
    """Reject an interpretation whose insights cite fact ids that were not measured."""
    known = {fact.id for fact in facts}
    sections = (
        interpretation.strategy_behavior,
        interpretation.strengths,
        interpretation.weaknesses,
        interpretation.risk_factors,
        interpretation.limitations,
    )
    unknown = sorted({fact_id for section in sections for insight in section for fact_id in insight.evidence} - known)
    if unknown:
        logger.warning("AI analysis cited unknown facts", extra={"unknown_fact_ids": unknown})
        raise InvalidAnalysis("The AI provider returned an analysis that cites facts that were not measured.")

"""Production startup checks (Phase 5A): refuse to start with a configuration that would fail or lose data later.

Development and test need nothing extra. Production must state, explicitly:
- VEKTOR_CORS_ORIGINS: the browser origins allowed to call the API. `[]` is a valid, deliberate answer (no browser
  origin, e.g. a same-origin proxy); forgetting the setting is not.
- VEKTOR_PORTFOLIO_DB_PATH and VEKTOR_BACKTEST_DB_PATH: where paper portfolios and backtests live. Their defaults sit
  inside the application directory, which a container discards on every deploy. The market data cache is disposable,
  so its default is allowed.
- An AI key when VEKTOR_AI_PROVIDER=anthropic: VEKTOR_AI_API_KEY or the SDK's own ANTHROPIC_API_KEY.

Every database directory must be creatable and writable in every environment. All problems are reported at once,
by setting name; values, and secrets in particular, are never echoed.
"""

import logging
import os
from pathlib import Path

from app.config import Settings

logger = logging.getLogger("vektor")

REQUIRED_IN_PRODUCTION = {
    "cors_origins": "VEKTOR_CORS_ORIGINS must be set: a JSON list of the exact https origins of your frontend "
                    '(use [] to allow no browser origin).',
    "portfolio_db_path": "VEKTOR_PORTFOLIO_DB_PATH must be set to a file on persistent storage (paper portfolios).",
    "backtest_db_path": "VEKTOR_BACKTEST_DB_PATH must be set to a file on persistent storage (stored backtests).",
}
class StartupConfigurationError(RuntimeError):
    """The settings cannot run safely; the message lists every problem by setting name."""


def configuration_problems(settings: Settings) -> list[str]:
    if settings.environment != "production":
        return []
    problems = [message for field, message in REQUIRED_IN_PRODUCTION.items() if field not in settings.model_fields_set]
    if settings.ai_provider == "anthropic" and settings.ai_api_key is None and not os.environ.get("ANTHROPIC_API_KEY"):
        problems.append("VEKTOR_AI_PROVIDER=anthropic needs an API key: set VEKTOR_AI_API_KEY (or ANTHROPIC_API_KEY) "
                        "as a secret, or set VEKTOR_AI_PROVIDER=none.")
    return problems

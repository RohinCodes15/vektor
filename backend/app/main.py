import logging
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analysis.provider import AnalysisProvider, AnthropicProvider
from app.analysis.service import AnalysisService
from app.api_errors import register_error_handlers
from app.backtest.service import BacktestService
from app.backtest.store import BacktestStore
from app.config import Settings, get_settings
from app.contracts import HealthResponse
from app.logging_config import configure_logging
from app.market_data.cache import HistoryCache
from app.market_data.provider import HistoryProvider, YFinanceProvider
from app.market_data.service import MarketDataService
from app.middleware import ExpensiveConcurrencyLimit, RateLimit, RequestBodyLimit, SecurityHeaders
from app.portfolio.service import PortfolioService
from app.portfolio.store import PortfolioStore
from app.routers import backtests, market, portfolios

try:
    VERSION = version("vektor-backend")
except PackageNotFoundError:
    VERSION = "0.1.0"

v1 = APIRouter(prefix="/api/v1")


@v1.get("/health", response_model=HealthResponse, tags=["system"])
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=VERSION,
        environment=settings.environment,
        trading_mode=settings.trading_mode,
    )


v1.include_router(market.router)
v1.include_router(portfolios.router)
v1.include_router(backtests.router)


def build_analysis_provider(settings: Settings) -> AnalysisProvider | None:
    """The configured AI provider, or None when AI analysis is off (the default)."""
    if settings.ai_provider == "none":
        return None
    key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else None
    return AnthropicProvider(settings.ai_model, key, settings.ai_timeout_seconds)


def add_middleware(app: FastAPI, settings: Settings) -> None:
    """Innermost first: each later middleware wraps the ones before it, so CORS headers reach every response."""
    app.add_middleware(RequestBodyLimit, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(ExpensiveConcurrencyLimit, max_concurrent=settings.max_concurrent_expensive_requests)
    app.add_middleware(
        RateLimit,
        per_minute=settings.rate_limit_per_minute,
        expensive_per_minute=settings.expensive_rate_limit_per_minute,
    )
    app.add_middleware(SecurityHeaders, hsts=settings.environment == "production")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )


def create_app(
    settings: Settings | None = None,
    *,
    market_data_provider: HistoryProvider | None = None,
    analysis_provider: AnalysisProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    docs = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version=VERSION,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    add_middleware(app, settings)
    register_error_handlers(app)
    market_data_service = MarketDataService(
        provider=market_data_provider or YFinanceProvider(),
        cache=HistoryCache(settings.market_data_cache_path),
        cache_ttl=timedelta(hours=settings.market_data_cache_ttl_hours),
    )
    app.state.market_data_service = market_data_service
    app.state.portfolio_service = PortfolioService(PortfolioStore(settings.portfolio_db_path), market_data_service)
    backtest_service = BacktestService(
        BacktestStore(settings.backtest_db_path),
        market_data_service,
        max_range_days=settings.max_backtest_range_days,
    )
    app.state.backtest_service = backtest_service
    provider = analysis_provider or build_analysis_provider(settings)
    app.state.analysis_service = AnalysisService(backtest_service, provider)
    app.include_router(v1)
    app.dependency_overrides[get_settings] = lambda: settings
    logging.getLogger("vektor").info(
        "app configured",
        extra={
            "environment": settings.environment,
            "trading_mode": settings.trading_mode,
            "ai_provider": settings.ai_provider,
            "docs_enabled": settings.docs_enabled,
            "cors_origins": len(settings.cors_origins),
        },
    )
    return app


app = create_app()

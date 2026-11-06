import logging
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.contracts import HealthResponse
from app.logging_config import configure_logging

try:
    VERSION = version("vektor-backend")
except PackageNotFoundError:
    VERSION = "0.1.0"

v1 = APIRouter(prefix="/api/v1")


@v1.get("/health", response_model=HealthResponse, tags=["system"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=VERSION,
        environment=settings.environment,
        trading_mode=settings.trading_mode,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title=settings.app_name, version=VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(v1)
    app.dependency_overrides[get_settings] = lambda: settings
    logging.getLogger("vektor").info(
        "app configured", extra={"environment": settings.environment, "trading_mode": settings.trading_mode}
    )
    return app


app = create_app()

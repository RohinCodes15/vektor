"""Shared API contracts (v1). Coordinated with frontend/ — see AGENTS.md before changing.

Simulation models are contracts only; no endpoints serve them yet.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TradingMode = Literal["paper"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(Contract):
    status: Literal["ok"]
    app: str
    version: str
    environment: str
    trading_mode: TradingMode


class SimulationCreate(Contract):
    symbols: list[str] = Field(min_length=1, max_length=50)
    starting_cash: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    start: datetime
    end: datetime
    strategy: str = Field(min_length=1, max_length=100)


class Simulation(Contract):
    id: UUID
    status: Literal["pending", "running", "completed", "failed"]
    mode: TradingMode = "paper"
    config: SimulationCreate
    created_at: datetime


class PaperOrder(Contract):
    symbol: str = Field(min_length=1, max_length=10)
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)
    type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = Field(default=None, gt=0)


class ErrorResponse(Contract):
    detail: str

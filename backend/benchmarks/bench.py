"""Reproducible benchmarks for the expensive API workloads. Offline: a seeded, deterministic price provider replaces
Yahoo Finance, so timings measure Vektor itself and every run computes the same results.

    uv run python benchmarks/bench.py            # table of median timings, response sizes and result fingerprints
    uv run python benchmarks/bench.py --repeat 9 # more repetitions per workload
    uv run python benchmarks/bench.py --memory   # peak Python allocation per workload instead (tracemalloc; slow)

Each workload goes through the HTTP API (validation, simulation, serialization) with a fresh temporary database.
The fingerprint is a SHA-256 of the response with run-specific fields (ids, timestamps) removed: it must not change
when an optimization is applied, which proves financial results are identical.
"""

import argparse
import hashlib
import json
import logging
import random
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.contracts import MarketDataSource, PriceBar  # noqa: E402
from app.main import create_app  # noqa: E402
from app.market_data.provider import ProviderHistory  # noqa: E402

FIRST_DAY = date(2005, 1, 3)
LAST_DAY = date(2024, 12, 31)  # 20 years of weekdays, about 5,200 bars per symbol
VOLATILE_FIELDS = {"id", "created_at", "fetched_at", "cached"}


class SeededProvider:
    """Deterministic random-walk bars per symbol; adjusted closes drift from closes like real dividends do."""

    source: MarketDataSource = "yahoo_finance"

    def __init__(self, latency_seconds: float = 0.0) -> None:
        self._latency_seconds = latency_seconds  # simulated network round trip per fetch
        self._bars: dict[str, tuple[PriceBar, ...]] = {}

    def fetch_daily_history(self, symbol: str, start: date, end: date) -> ProviderHistory:
        time.sleep(self._latency_seconds)
        bars = self._bars.setdefault(symbol, _walk(symbol))
        return ProviderHistory("USD", tuple(bar for bar in bars if start <= bar.date <= end))


def _walk(symbol: str) -> tuple[PriceBar, ...]:
    rng = random.Random(symbol)
    price, factor, day, bars = 50.0, 0.8, FIRST_DAY, []
    while day <= LAST_DAY:
        if day.weekday() < 5:
            open_ = price
            price = max(1.0, price * (1 + rng.gauss(0.0003, 0.015)))
            high = max(open_, price) * (1 + abs(rng.gauss(0, 0.004)))
            low = min(open_, price) * (1 - abs(rng.gauss(0, 0.004)))
            factor = min(1.0, factor + 0.00004)
            bars.append(PriceBar(date=day, open=round(open_, 4), high=round(high, 4), low=round(low, 4),
                                 close=round(price, 4), adjusted_close=round(price * factor, 4),
                                 volume=rng.randint(100_000, 5_000_000)))
        day += timedelta(days=1)
    return tuple(bars)


@dataclass(frozen=True)
class Result:
    name: str
    median_ms: float
    min_ms: float
    bytes: int
    wire_bytes: int  # as sent: compressed when the server gzips the response
    fingerprint: str


def _fingerprint(payload: Any) -> str:
    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in VOLATILE_FIELDS}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    return hashlib.sha256(json.dumps(strip(payload), sort_keys=True).encode()).hexdigest()[:16]


def _client(tmp: Path, latency_seconds: float = 0.0) -> TestClient:
    settings = Settings(
        environment="test",
        log_level="ERROR",
        market_data_cache_path=tmp / "market.sqlite3",
        portfolio_db_path=tmp / "portfolios.sqlite3",
        backtest_db_path=tmp / "backtests.sqlite3",
        rate_limit_per_minute=0,
        expensive_rate_limit_per_minute=0,
    )
    return TestClient(create_app(settings, market_data_provider=SeededProvider(latency_seconds)))


def _peak_memory(name: str, call: Callable[[int], Any]) -> str:
    """Peak Python memory allocated while serving one request, warmed up once so caches are already loaded."""
    call(0)
    tracemalloc.start()
    call(1)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return f"{name:32} {peak / 1024 / 1024:9.1f} MiB peak"


def _measure(name: str, repeat: int, call: Callable[[int], Any]) -> Result:
    timings, response = [], None
    for i in range(repeat):
        started = time.perf_counter()
        response = call(i)
        timings.append((time.perf_counter() - started) * 1000)
    if response is None or response.status_code >= 300:
        raise SystemExit(f"{name} failed: {getattr(response, 'status_code', None)} {getattr(response, 'text', '')}")
    return Result(name, statistics.median(timings), min(timings), len(response.content),
                  response.num_bytes_downloaded, _fingerprint(response.json()))


SETTINGS = {"starting_cash": "100000.00", "fee_per_trade": "1.00", "fee_bps": "5", "slippage_bps": "10"}
SPAN_20Y = {"start": "2005-01-03", "end": "2024-12-31"}


PROVIDER_LATENCY_SECONDS = 0.25


def cold_workloads(client: TestClient) -> dict[str, Callable[[int], Any]]:
    """Uncached symbols behind a provider with PROVIDER_LATENCY_SECONDS of simulated latency per fetch."""
    return {
        "backtest_cold_5sym_10y_latency": lambda i: client.post("/api/v1/backtests", json={
            **SETTINGS, "start": "2015-01-02", "end": "2024-12-31",
            "symbols": [f"C{i}S{n}" for n in range(5)], "strategy": {"kind": "buy_and_hold"}}),
    }


def workloads(client: TestClient) -> dict[str, Callable[[int], Any]]:
    history_20y = {"start": "2005-01-03", "end": "2024-12-31"}
    sma_grid = {"kind": "sma_crossover", "fast_windows": [5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
                "slow_windows": [60, 80, 100, 120, 140, 160, 180, 200, 220, 240]}
    rsi_grid = {"kind": "rsi", "periods": [7, 10, 14, 21],
                "oversold": [20, 25, 30, 35, 40], "overbought": [60, 65, 70, 75, 80]}
    return {
        "history_uncached_20y": lambda i: client.get(
            "/api/v1/market/history", params={"symbol": f"UNC{i}", **history_20y}),
        "history_cached_20y": lambda i: client.get(
            "/api/v1/market/history", params={"symbol": "AAA", **history_20y}),
        "backtest_3sym_20y_sma": lambda i: client.post("/api/v1/backtests", json={
            **SETTINGS, **SPAN_20Y, "symbols": ["AAA", "BBB", "CCC"],
            "strategy": {"kind": "sma_crossover", "fast_window": 20, "slow_window": 50}}),
        "comparison_5_strategies_20y": lambda i: client.post("/api/v1/backtests/comparisons", json={
            **SETTINGS, **SPAN_20Y, "symbol": "AAA", "strategies": [
                {"kind": "buy_and_hold"},
                {"kind": "sma_crossover", "fast_window": 20, "slow_window": 50},
                {"kind": "sma_crossover", "fast_window": 50, "slow_window": 200},
                {"kind": "rsi", "period": 14, "oversold": 30, "overbought": 70},
                {"kind": "rsi", "period": 7, "oversold": 25, "overbought": 75}]}),
        "optimization_sma_100_20y": lambda i: client.post("/api/v1/backtests/optimizations", json={
            **SETTINGS, **SPAN_20Y, "symbol": "AAA", "grid": sma_grid, "objective": "sharpe_ratio"}),
        "optimization_rsi_100_20y": lambda i: client.post("/api/v1/backtests/optimizations", json={
            **SETTINGS, **SPAN_20Y, "symbol": "AAA", "grid": rsi_grid, "objective": "total_return_pct"}),
        "list_backtests_50": lambda i: client.get("/api/v1/backtests"),
        "get_backtest_20y": lambda i: client.get(f"/api/v1/backtests/{client.backtest_id}"),  # type: ignore[attr-defined]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--json", type=Path, help="also write the results to this file")
    parser.add_argument("--memory", action="store_true", help="report peak memory per workload instead of timings")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory() as tmp:
        client = _client(Path(tmp))
        # Warm the market data cache and store 50 backtests so list and get measure realistic stores.
        for _ in range(50):
            run = workloads(client)["backtest_3sym_20y_sma"](0)
        client.backtest_id = run.json()["id"]  # type: ignore[attr-defined]
        if args.memory:
            for name, call in workloads(client).items():
                print(_peak_memory(name, call))
            return
        results = [_measure(name, args.repeat, call) for name, call in workloads(client).items()]
    with tempfile.TemporaryDirectory() as tmp:
        cold = _client(Path(tmp), PROVIDER_LATENCY_SECONDS)
        results += [_measure(name, args.repeat, call) for name, call in cold_workloads(cold).items()]
    print(f"{'workload':32} {'median ms':>10} {'min ms':>9} {'json bytes':>11} {'wire bytes':>11}  fingerprint")
    for r in results:
        print(f"{r.name:32} {r.median_ms:10.1f} {r.min_ms:9.1f} {r.bytes:11,} {r.wire_bytes:11,}  {r.fingerprint}")
    if args.json:
        args.json.write_text(json.dumps([r.__dict__ for r in results], indent=2) + "\n")


if __name__ == "__main__":
    main()

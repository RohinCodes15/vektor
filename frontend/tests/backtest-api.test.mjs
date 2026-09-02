import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, runBacktest } from "../src/lib/api.ts";

const config = {
  symbols: ["AAPL"], start: "2024-01-01", end: "2024-02-01", starting_cash: "10000.00",
  strategy: { kind: "buy_and_hold" }, position_size_pct: "100", fee_per_trade: "0.00", fee_bps: "0", slippage_bps: "0",
};
const result = {
  id: "123e4567-e89b-12d3-a456-426614174000", mode: "paper", currency: "USD", config,
  created_at: "2024-02-02T12:00:00Z", source: "yahoo_finance", bars: 2, first_date: "2024-01-02", last_date: "2024-01-03",
  metrics: { final_equity: "10000.00", total_return_pct: "0", annualized_return_pct: null, volatility_pct: null, max_drawdown_pct: "0", sharpe_ratio: null, win_rate_pct: null, trades: 0, closed_trades: 0, winning_trades: 0, total_fees: "0.00" },
  warnings: ["Annualized return is unavailable."],
  equity_curve: [{ date: "2024-01-02", cash: "10000.00", positions_value: "0.00", equity: "10000.00", drawdown_pct: "0" }],
  trades: [], rejected_orders: [], open_positions: [],
};

test("runBacktest validates, normalizes, and posts exact decimal strings", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.pathname, "/api/v1/backtests");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["content-type"], "application/json");
    assert.equal(options.credentials, "omit");
    assert.deepEqual(JSON.parse(options.body), { ...config, symbols: ["AAPL"] });
    return Response.json(result, { status: 201 });
  });
  assert.deepEqual(await runBacktest({ ...config, symbols: [" aapl "] }), result);
});

test("runBacktest accepts unavailable metrics and rejects incompatible results", async (t) => {
  const request = t.mock.method(globalThis, "fetch", async () => Response.json(result));
  assert.equal((await runBacktest(config)).metrics.sharpe_ratio, null);
  for (const bad of [
    { mode: "live" }, { secret: "leaked" }, { metrics: { ...result.metrics, final_equity: null } },
    { config: { ...config, starting_cash: "0.00" } },
    { config: { ...config, strategy: { kind: "sma_crossover", fast_window: 50, slow_window: 20 } } },
  ]) {
    request.mock.mockImplementation(async () => Response.json({ ...result, ...bad }));
    await assert.rejects(runBacktest(config), /incompatible backtest result/);
  }
});

test("runBacktest rejects invalid configuration before requesting", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  await assert.rejects(runBacktest({ ...config, symbols: ["AAPL", "aapl"] }), /distinct/);
  await assert.rejects(runBacktest({ ...config, strategy: { kind: "sma_crossover", fast_window: 50, slow_window: 20 } }), /SMA windows/);
  await assert.rejects(runBacktest({ ...config, end: new Date().toISOString().slice(0, 10) }), /before today/);
  assert.equal(request.mock.callCount(), 0);
});

test("runBacktest maps API failures without exposing response bodies", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("private provider details", { status: 422 }));
  await assert.rejects(runBacktest(config), (error) => error instanceof ApiError && error.statusCode === 422 && !error.message.includes("private"));
});

test("backtests receive a simulation-sized timeout", async (t) => {
  t.mock.method(AbortSignal, "timeout", (milliseconds) => {
    assert.equal(milliseconds, 30000);
    return AbortSignal.abort(new DOMException("timeout", "TimeoutError"));
  });
  t.mock.method(globalThis, "fetch", async (_url, { signal }) => { throw signal.reason; });
  await assert.rejects(runBacktest(config), /backtest request timed out/);
});

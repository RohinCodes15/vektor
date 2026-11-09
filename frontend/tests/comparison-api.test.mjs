import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, runBacktestComparison, runBacktestOptimization } from "../src/lib/api.ts";

const strategies = [{ kind: "buy_and_hold" }, { kind: "sma_crossover", fast_window: 2, slow_window: 3 }];
const config = {
  symbol: "AAPL", strategies, start: "2024-01-01", end: "2024-02-01", starting_cash: "10000.00",
  position_size_pct: "100", fee_per_trade: "0.00", fee_bps: "0", slippage_bps: "0",
};
const metrics = { final_equity: "10000.00", total_return_pct: "0", annualized_return_pct: null, volatility_pct: null, max_drawdown_pct: "0", sharpe_ratio: null, win_rate_pct: null, trades: 0, closed_trades: 0, winning_trades: 0, total_fees: "0.00" };
const differences = { total_return_pct: "0", annualized_return_pct: null, volatility_pct: null, max_drawdown_pct: "0", sharpe_ratio: null, win_rate_pct: null };
const result = {
  mode: "paper", currency: "USD", source: "yahoo_finance", config, bars: 2,
  first_date: "2024-01-02", last_date: "2024-01-03", dates: ["2024-01-02", "2024-01-03"],
  results: strategies.map((strategy) => ({ strategy, status: "available", unavailable_reason: null, metrics, warnings: [], equity: ["10000.00", "10000.00"], vs_baseline: differences })),
  leaders: Object.keys(differences).map((metric) => ({ metric, better: metric === "volatility_pct" ? "lower" : "higher", leaders: [], reason: "Insufficient observations or equal values." })),
  disclaimer: "Past paper performance is not a forecast.",
};
function unavailable(strategy) {
  return { strategy, status: "unavailable", unavailable_reason: "Too few bars for warm-up.", metrics: null, warnings: [], equity: null, vs_baseline: null };
}

test("comparison posts shared settings, preserves decimals, and normalizes the ticker", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.pathname, "/api/v1/backtests/comparisons");
    assert.equal(options.method, "POST");
    assert.equal(options.credentials, "omit");
    assert.equal(options.cache, "no-store");
    assert.equal(options.redirect, "error");
    assert.equal(options.headers["content-type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), config);
    return Response.json(result);
  });
  assert.deepEqual(await runBacktestComparison({ ...config, symbol: " aapl " }), result);
});

test("comparison accepts 2–5 configurations, defaults, and distinct parameters of the same strategy", async (t) => {
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const query = JSON.parse(options.body);
    return Response.json({ ...result, config: query, results: query.strategies.map(unavailable) });
  });
  const five = [strategies[0], strategies[1], { kind: "sma_crossover", fast_window: 3, slow_window: 4 }, { kind: "rsi", period: 2, oversold: "30", overbought: "70" }, { kind: "rsi", period: 3, oversold: "30", overbought: "70" }];
  assert.equal((await runBacktestComparison({ ...config, strategies: five })).results.length, 5);
  t.mock.method(globalThis, "fetch", async () => Response.json({ ...result, config: { ...config, strategies: [strategies[0], { kind: "sma_crossover", fast_window: 20, slow_window: 50 }] }, results: [unavailable(strategies[0]), unavailable({ kind: "sma_crossover", fast_window: 20, slow_window: 50 })] }));
  const minimal = { symbol: config.symbol, start: config.start, end: config.end, starting_cash: config.starting_cash };
  assert.equal((await runBacktestComparison({ ...minimal, strategies: [strategies[0], { kind: "sma_crossover" }] })).results[1].status, "unavailable");
});

test("optimization preserves specific 422 validation messages and falls back for malformed errors", async (t) => {
  const query = { symbol: config.symbol, start: config.start, end: config.end, starting_cash: config.starting_cash,
    grid: { kind: "sma_crossover", fast_windows: [2], slow_windows: [3] }, objective: "total_return_pct" };
  const detail = "The test segment has too few trading days for the selected grid.";
  const request = t.mock.method(globalThis, "fetch", async () => Response.json({ detail }, { status: 422 }));
  await assert.rejects(runBacktestOptimization(query), (error) => error instanceof ApiError && error.statusCode === 422 && error.message === detail);
  for (const body of ["not JSON", "null", JSON.stringify({ detail: [] }), JSON.stringify({ detail: " " }), JSON.stringify({ message: "private details" })]) {
    request.mock.mockImplementation(async () => new Response(body, { status: 422 }));
    await assert.rejects(runBacktestOptimization(query), (error) => error instanceof ApiError && error.statusCode === 422
      && error.message === "Optimization was rejected. Check the parameter grid, objective, train/test split, dates, and costs.");
  }
  request.mock.mockImplementation(async () => Response.json({ detail }, { status: 503 }));
  await assert.rejects(runBacktestOptimization(query), (error) => error instanceof ApiError && error.statusCode === 503 && error.message === "The market data provider is unavailable. Try again later.");
});

test("comparison rejects invalid input and semantic duplicates before fetching", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const bad of [
    { strategies: [strategies[0]] }, { strategies: Array(6).fill(strategies[0]) },
    { strategies: [strategies[0], strategies[0]] },
    { strategies: [{ kind: "sma_crossover" }, { kind: "sma_crossover", slow_window: 50, fast_window: 20 }] },
    { strategies: [{ kind: "rsi" }, { kind: "rsi", period: 14, oversold: "30.00", overbought: "70" }] },
    { strategies: [strategies[0], { kind: "rsi", oversold: "80", overbought: "70" }] },
    { strategies: [strategies[0], { kind: "sma_crossover", fast_window: 50, slow_window: 20 }] },
    { symbol: "^GSPC" }, { starting_cash: "0" }, { fee_bps: "1001" }, { position_size_pct: "101" },
    { end: config.start }, { end: new Date().toISOString().slice(0, 10) },
  ]) await assert.rejects(runBacktestComparison({ ...config, ...bad }));
  assert.equal(request.mock.callCount(), 0);
});

test("comparison preserves insufficient-data results and unavailable baselines without inventing values", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const results of [
    [result.results[0], unavailable(strategies[1])],
    [unavailable(strategies[0]), { ...result.results[1], vs_baseline: null }],
    strategies.map(unavailable),
  ]) {
    request.mock.mockImplementation(async () => Response.json({ ...result, results }));
    assert.deepEqual((await runBacktestComparison(config)).results, results);
  }
});

test("comparison validates alignment, exact fields, config echo, metrics, relative values, and leaders", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const bad of [
    { extra: true }, { mode: "live" }, { source: "fabricated" }, { currency: "EUR" },
    { bars: 0 }, { bars: 3 }, { dates: ["2024-01-03", "2024-01-02"] }, { dates: ["2024-01-02", "2024-01-02"] },
    { dates: ["2024-01-02", "2024-02-30"] }, { first_date: "2024-01-01" },
    { config: { ...config, starting_cash: "20000.00" } }, { config: { ...config, symbol: "MSFT" } },
    { config: { ...config, extra: true } }, { config: { ...config, strategies: [strategies[1], strategies[0]] } },
    { results: [result.results[0]] }, { results: [null, result.results[1]] },
    ...[
      { strategy: strategies[0] }, { equity: ["10000.00"] }, { equity: ["10000.00", 10000] },
      { metrics: { ...metrics, volatility_pct: "-1" } }, { warnings: [1] }, { status: "pending" },
      { vs_baseline: null }, { vs_baseline: { ...differences, total_return_pct: null } },
      { vs_baseline: { ...differences, sharpe_ratio: "0" } }, { vs_baseline: { ...differences, total_return_pct: 1 } },
      { ...unavailable(strategies[1]), equity: [] }, { ...unavailable(strategies[1]), unavailable_reason: null },
    ].map((patch) => ({ results: [result.results[0], { ...result.results[1], ...patch }] })),
    { leaders: [{ metric: "total_return_pct", better: "higher", leaders: [2], reason: null }] },
    { leaders: [{ metric: "sharpe_ratio", better: "higher", leaders: [0], reason: null }] },
    { leaders: [{ metric: "volatility_pct", better: "higher", leaders: [], reason: "Equal" }] },
    { leaders: [{ metric: "invented", better: "higher", leaders: [], reason: "Equal" }] },
    { leaders: [{ metric: "total_return_pct", better: "higher", leaders: [], reason: null }] },
    { leaders: [result.leaders[0], result.leaders[0]] }, { disclaimer: null },
  ]) {
    request.mock.mockImplementation(async () => Response.json({ ...result, ...bad }));
    await assert.rejects(runBacktestComparison(config), /incompatible strategy comparison/);
  }
});

test("comparison accepts signed differences and tied metric leaders", async (t) => {
  const query = { ...config, strategies: [...strategies, { kind: "rsi", period: 2, oversold: "30", overbought: "70" }] };
  const results = query.strategies.map((strategy, index) => ({ ...result.results[0], strategy,
    metrics: { ...metrics, total_return_pct: index === 2 ? "-1" : "2", final_equity: index === 2 ? "9900.00" : "10200.00" },
    equity: ["10000.00", index === 2 ? "9900.00" : "10200.00"],
    vs_baseline: { ...differences, total_return_pct: index === 2 ? "-3" : "0" },
  }));
  const response = { ...result, config: query, results, leaders: [{ metric: "total_return_pct", better: "higher", leaders: [0, 1], reason: null }] };
  t.mock.method(globalThis, "fetch", async () => Response.json(response));
  assert.deepEqual(await runBacktestComparison(query), response);
});

test("comparison maps HTTP failures safely and rejects network and malformed JSON responses", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const status of [404, 422, 502, 503, 500]) {
    request.mock.mockImplementation(async () => new Response("private provider data", { status }));
    await assert.rejects(runBacktestComparison(config), (error) => error instanceof ApiError && error.statusCode === status && !error.message.includes("private"));
  }
  request.mock.mockImplementation(async () => { throw new Error("private"); });
  await assert.rejects(runBacktestComparison(config), /could not be reached/);
  request.mock.mockImplementation(async () => new Response("not JSON"));
  await assert.rejects(runBacktestComparison(config), /invalid strategy comparison response/);
});

test("comparison uses backtest timeout and preserves cancellation", async (t) => {
  t.mock.method(AbortSignal, "timeout", (milliseconds) => {
    assert.equal(milliseconds, 30000);
    return AbortSignal.abort(new DOMException("timeout", "TimeoutError"));
  });
  t.mock.method(globalThis, "fetch", async (_url, { signal }) => { throw signal.reason; });
  await assert.rejects(runBacktestComparison(config), /strategy comparison request timed out/);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(runBacktestComparison(config, controller.signal), (error) => error === controller.signal.reason);
});

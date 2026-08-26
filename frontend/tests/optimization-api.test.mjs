import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, runBacktestOptimization } from "../src/lib/api.ts";

const grid = { kind: "sma_crossover", fast_windows: [2], slow_windows: [3] };
const config = { symbol: "AAPL", start: "2024-01-01", end: "2024-02-01", starting_cash: "10000.00", grid, objective: "total_return_pct", train_pct: 70, top_n: 10, position_size_pct: "100", fee_per_trade: "0.00", fee_bps: "0", slippage_bps: "0" };
const strategy = { kind: "sma_crossover", fast_window: 2, slow_window: 3 };
const metrics = { final_equity: "10000.00", total_return_pct: "0.0000", annualized_return_pct: null, volatility_pct: null, max_drawdown_pct: "0.0000", sharpe_ratio: null, win_rate_pct: null, trades: 0, closed_trades: 0, winning_trades: 0, total_fees: "0.00" };
function segment(dates) {
  return { first_date: dates[0], last_date: dates.at(-1), bars: dates.length, metrics, warnings: ["Sharpe ratio is undefined."], equity_curve: dates.map((date) => ({ date, cash: "10000.00", positions_value: "0.00", equity: "10000.00", drawdown_pct: "0.0000" })) };
}
const train = segment(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10"]);
const testSegment = segment(["2024-01-11", "2024-01-12", "2024-01-16"]);
const result = {
  mode: "paper", currency: "USD", source: "yahoo_finance", config, bars: 10,
  split: { train_pct: 70, train_bars: 7, train_first_date: train.first_date, train_last_date: train.last_date, test_bars: 3, test_first_date: testSegment.first_date, test_last_date: testSegment.last_date },
  better: "higher", candidates_total: 1, candidates_evaluated: 1, candidates_skipped: 0, candidates_unranked: 0,
  ranked: [{ rank: 1, strategy, objective_value: "0.0000", train_metrics: metrics }],
  selected: { strategy, train, test: testSegment, overfitting: { annualized_return_gap_pct: null, sharpe_gap: null, max_drawdown_gap_pct: "0.0000", flags: [{ code: "few_trades", message: "Too few trades to assess robustness." }] } },
  selection_reason: null, limitations: ["Grid search can overfit."], disclaimer: "Past paper results are not forecasts.",
};
const insufficient = { ...result, ranked: [], selected: null, selection_reason: "No candidate has a defined training objective.", candidates_unranked: 1 };

test("optimization posts the versioned request, defaults and exact decimals without credentials", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.pathname, "/api/v1/backtests/optimizations");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["content-type"], "application/json");
    assert.equal(options.credentials, "omit");
    assert.equal(options.cache, "no-store");
    assert.equal(options.redirect, "error");
    assert.deepEqual(JSON.parse(options.body), config);
    return Response.json(result);
  });
  const minimal = { start: config.start, end: config.end, starting_cash: config.starting_cash, grid, objective: config.objective };
  assert.deepEqual(await runBacktestOptimization({ ...minimal, symbol: " aapl " }), result);
});

test("optimization supports RSI grids, all objectives, sorted ranges, skipped invalid pairs, and insufficient data", async (t) => {
  const request = t.mock.method(globalThis, "fetch", async (_url, options) => {
    const query = JSON.parse(options.body);
    assert.deepEqual(query.grid, { kind: "rsi", periods: [2, 3], oversold: ["30", "80"], overbought: ["70"] });
    return Response.json({ ...insufficient, config: query, candidates_total: 2, candidates_evaluated: 0, candidates_skipped: 2, candidates_unranked: 0 });
  });
  for (const objective of ["total_return_pct", "sharpe_ratio", "max_drawdown_pct"]) {
    const response = await runBacktestOptimization({ ...config, objective, grid: { kind: "rsi", periods: [3, 2], oversold: ["80", "30"], overbought: ["70"] } });
    assert.equal(response.selected, null);
    assert.equal(response.candidates_skipped, 2);
    assert.equal(response.selection_reason, insufficient.selection_reason);
  }
  request.mock.mockImplementation(async (_url, options) => {
    const query = JSON.parse(options.body);
    assert.deepEqual(query.grid.fast_windows, [2, 4]);
    return Response.json({ ...result, config: query });
  });
  await runBacktestOptimization({ ...config, grid: { kind: "sma_crossover", fast_windows: [4, 2], slow_windows: [3] } });
});

test("optimization rejects invalid grids, excessive workloads, split settings, objectives, and shared inputs before fetching", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const bad of [
    { grid: { ...grid, fast_windows: [] } }, { grid: { ...grid, fast_windows: [2, 2] } },
    { grid: { ...grid, fast_windows: [1] } }, { grid: { ...grid, slow_windows: [501] } },
    { grid: { ...grid, fast_windows: [4], slow_windows: [3] } }, { grid: { ...grid, extra: true } },
    { grid: { ...grid, fast_windows: Array.from({ length: 21 }, (_, i) => i + 2) } },
    { grid: { kind: "sma_crossover", fast_windows: Array.from({ length: 11 }, (_, i) => i + 2), slow_windows: Array.from({ length: 10 }, (_, i) => i + 30) } },
    { grid: { kind: "rsi", periods: [14], oversold: ["30", "30.00"], overbought: ["70"] } },
    { grid: { kind: "rsi", periods: [1], oversold: ["30"], overbought: ["70"] } },
    { grid: { kind: "rsi", periods: [14], oversold: ["30.001"], overbought: ["70"] } },
    { grid: { kind: "rsi", periods: [14], oversold: ["80"], overbought: ["70"] } },
    { objective: "invented" }, { train_pct: 49 }, { train_pct: 91 }, { train_pct: 70.5 }, { top_n: 0 }, { top_n: 101 },
    { symbol: "^GSPC" }, { starting_cash: "0" }, { fee_bps: "1001" }, { end: config.start },
  ]) await assert.rejects(runBacktestOptimization({ ...config, ...bad }));
  assert.equal(request.mock.callCount(), 0);
});

test("optimization validates nested fields, ranked candidates, chronological curves and overfitting indicators", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const bad of [
    { extra: true }, { mode: "live" }, { better: "lower" }, { config: { ...config, symbol: "MSFT" } },
    { config: { ...config, grid: { ...grid, slow_windows: [4] } } }, { config: { ...config, train_pct: 80 } },
    { bars: 11 }, { split: { ...result.split, test_first_date: train.last_date } },
    { candidates_total: 2 }, { candidates_evaluated: 2 }, { candidates_skipped: -1 }, { candidates_unranked: 2 },
    { ranked: [{ ...result.ranked[0], rank: 2 }] }, { ranked: [{ ...result.ranked[0], objective_value: "1" }] },
    { ranked: [{ ...result.ranked[0], strategy: { ...strategy, fast_window: 3, slow_window: 4 } }] },
    { ranked: [{ ...result.ranked[0], train_metrics: { ...metrics, max_drawdown_pct: "1" } }] },
    { selected: null }, { selection_reason: "Unexpected" },
    { selected: { ...result.selected, strategy: { kind: "buy_and_hold" } } },
    ...[
      { bars: 8 }, { equity_curve: train.equity_curve.slice(1) },
      { equity_curve: train.equity_curve.map((point, index) => index === 1 ? { ...point, date: train.first_date } : point) },
      { equity_curve: train.equity_curve.map((point) => ({ ...point, equity: 10000 })) },
      { equity_curve: train.equity_curve.map((point) => ({ ...point, drawdown_pct: "1" })) },
      { metrics: { ...metrics, final_equity: null } }, { warnings: [1] },
    ].map((patch) => ({ selected: { ...result.selected, train: { ...train, ...patch } } })),
    { selected: { ...result.selected, overfitting: { ...result.selected.overfitting, sharpe_gap: "0" } } },
    { selected: { ...result.selected, overfitting: { ...result.selected.overfitting, max_drawdown_gap_pct: null } } },
    { selected: { ...result.selected, overfitting: { ...result.selected.overfitting, flags: [{ code: "invented", message: "unknown" }] } } },
    { limitations: [1] }, { disclaimer: null },
  ]) {
    request.mock.mockImplementation(async () => Response.json({ ...result, ...bad }));
    await assert.rejects(runBacktestOptimization(config), /incompatible strategy optimization/);
  }
});

test("optimization accepts ranked ties and signed drawdown objectives without reranking test performance", async (t) => {
  const query = { ...config, grid: { ...grid, fast_windows: [2, 3], slow_windows: [4] }, objective: "max_drawdown_pct" };
  const candidates = [2, 3].map((fast_window, index) => ({ rank: index + 1, strategy: { ...strategy, fast_window, slow_window: 4 }, objective_value: "-1.0000", train_metrics: { ...metrics, max_drawdown_pct: "-1.0000" } }));
  const selected = { ...result.selected, strategy: candidates[0].strategy, train: { ...train, metrics: candidates[0].train_metrics }, test: { ...testSegment, metrics: { ...metrics, max_drawdown_pct: "-2.0000" } }, overfitting: { ...result.selected.overfitting, max_drawdown_gap_pct: "-1.0000" } };
  const response = { ...result, config: query, candidates_total: 2, candidates_evaluated: 2, ranked: candidates, selected };
  t.mock.method(globalThis, "fetch", async () => Response.json(response));
  assert.deepEqual(await runBacktestOptimization(query), response);
});

test("optimization handles server, validation, network, malformed JSON, timeout, and cancellation failures safely", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const status of [404, 422, 502, 503, 500]) {
    request.mock.mockImplementation(async () => new Response("private server details", { status }));
    await assert.rejects(runBacktestOptimization(config), (error) => error instanceof ApiError && error.statusCode === status && !error.message.includes("private"));
  }
  request.mock.mockImplementation(async () => { throw new Error("private"); });
  await assert.rejects(runBacktestOptimization(config), /could not be reached/);
  request.mock.mockImplementation(async () => new Response("invalid JSON"));
  await assert.rejects(runBacktestOptimization(config), /invalid strategy optimization response/);
  t.mock.method(AbortSignal, "timeout", (milliseconds) => {
    assert.equal(milliseconds, 30000);
    return AbortSignal.abort(new DOMException("timeout", "TimeoutError"));
  });
  request.mock.mockImplementation(async (_url, { signal }) => { throw signal.reason; });
  await assert.rejects(runBacktestOptimization(config), /strategy optimization request timed out/);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(runBacktestOptimization(config, controller.signal), (error) => error === controller.signal.reason);
});

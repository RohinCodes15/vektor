import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, getBacktestAnalysis } from "../src/lib/api.ts";

const id = "123e4567-e89b-12d3-a456-426614174000";
const insight = { text: "The simulation held the position.", evidence: ["trades"] };
const available = {
  backtest_id: id, mode: "paper", status: "available", unavailable_reason: null,
  generated_at: "2026-11-07T12:00:00Z", provider: "anthropic", model: "configured-model",
  facts: [{ id: "trades", label: "Trades", value: "1" }],
  interpretation: { summary: "Educational explanation.", strategy_behavior: [insight], strengths: [], weaknesses: [], risk_factors: [], limitations: [insight] },
  disclaimer: "Educational only. Not investment advice.",
};
const unavailable = { ...available, status: "unavailable", unavailable_reason: "No provider configured.", provider: null, model: null, interpretation: null };

test("analysis posts without a body, keeps exact facts, and supports an unavailable provider", async (t) => {
  const request = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.pathname, `/api/v1/backtests/${id}/analysis`);
    assert.equal(options.method, "POST");
    assert.equal(options.body, undefined);
    assert.equal(options.headers, undefined);
    assert.equal(options.credentials, "omit");
    assert.equal(options.cache, "no-store");
    assert.equal(options.redirect, "error");
    return Response.json(available);
  });
  assert.deepEqual(await getBacktestAnalysis(id), available);
  request.mock.mockImplementation(async () => Response.json(unavailable));
  assert.deepEqual(await getBacktestAnalysis(id), unavailable);
});

test("analysis rejects incompatible fields, state combinations, and unmeasured evidence", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  const interpretation = available.interpretation;
  for (const bad of [
    { mode: "live" }, { extra: "unexpected" }, { backtest_id: "123e4567-e89b-12d3-a456-426614174001" },
    { generated_at: "2026-02-30T12:00:00Z" }, { generated_at: "2026-11-07T12:00:00" },
    { status: "pending" }, { provider: "other" }, { model: null }, { unavailable_reason: "failed" },
    { facts: [{ ...available.facts[0], value: 1 }] }, { facts: [...available.facts, ...available.facts] },
    { facts: [{ ...available.facts[0], extra: true }] }, { interpretation: null },
    { interpretation: { ...interpretation, summary: "" } },
    { interpretation: { ...interpretation, summary: "x".repeat(801) } },
    { interpretation: { ...interpretation, strategy_behavior: [] } },
    { interpretation: { ...interpretation, limitations: [] } },
    { interpretation: { ...interpretation, strengths: Array(6).fill(insight) } },
    { interpretation: { ...interpretation, weaknesses: [{ ...insight, text: "x".repeat(601) }] } },
    { interpretation: { ...interpretation, risk_factors: [{ ...insight, evidence: [] }] } },
    { interpretation: { ...interpretation, risk_factors: [{ ...insight, evidence: Array(7).fill("trades") }] } },
    { interpretation: { ...interpretation, limitations: [{ ...insight, evidence: ["invented"] }] } },
    { interpretation: { ...interpretation, extra: true } }, { disclaimer: null },
    { ...unavailable, provider: "anthropic" }, { ...unavailable, model: "model" },
    { ...unavailable, interpretation }, { ...unavailable, unavailable_reason: null },
  ]) {
    request.mock.mockImplementation(async () => Response.json({ ...available, ...bad }));
    await assert.rejects(getBacktestAnalysis(id), /incompatible backtest analysis/);
  }
});

test("analysis validates ids before fetching and maps HTTP errors without exposing bodies", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  await assert.rejects(getBacktestAnalysis("../other"), /valid backtest/);
  assert.equal(request.mock.callCount(), 0);
  for (const [status, message] of [[404, /no longer exists/], [422, /valid backtest/], [502, /invalid analysis/], [503, /AI provider is unavailable/], [500, /HTTP 500/]]) {
    request.mock.mockImplementation(async () => new Response("private provider details", { status }));
    await assert.rejects(getBacktestAnalysis(id), (error) => error instanceof ApiError && error.statusCode === status
      && message.test(error.message) && !error.message.includes("private"));
  }
});

test("analysis handles network errors and invalid JSON", async (t) => {
  const request = t.mock.method(globalThis, "fetch", async () => { throw new Error("private"); });
  await assert.rejects(getBacktestAnalysis(id), /could not be reached/);
  request.mock.mockImplementation(async () => new Response("not JSON"));
  await assert.rejects(getBacktestAnalysis(id), /invalid backtest analysis response/);
});

test("analysis allows time for provider retries and preserves caller cancellation", async (t) => {
  t.mock.method(AbortSignal, "timeout", (milliseconds) => {
    assert.equal(milliseconds, 300000);
    return AbortSignal.abort(new DOMException("timeout", "TimeoutError"));
  });
  t.mock.method(globalThis, "fetch", async (_url, { signal }) => { throw signal.reason; });
  await assert.rejects(getBacktestAnalysis(id), /backtest analysis request timed out/);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(getBacktestAnalysis(id, controller.signal), (error) => error === controller.signal.reason);
});

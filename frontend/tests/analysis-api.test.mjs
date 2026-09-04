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

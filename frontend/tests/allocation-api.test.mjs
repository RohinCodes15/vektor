import { test } from "node:test";
import assert from "node:assert/strict";
import { getPortfolioAllocation } from "../src/lib/api.ts";
import { id, other, allocation, cashOnly, unpriced } from "./allocation-fixtures.mjs";

test("allocation uses the read-only API and preserves exact weights", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.pathname, `/api/v1/portfolios/${id}/allocation`);
    assert.equal(options.method, "GET"); assert.equal(options.cache, "no-store"); assert.equal(options.credentials, "omit");
    return Response.json(allocation);
  });
  assert.deepEqual(await getPortfolioAllocation(id), allocation);
});

test("allocation accepts cash-only, zero equity and missing prices; rejects invalid weights", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const response of [cashOnly, unpriced, { ...cashOnly, cash: "0.00", equity: "0.00", cash_weight_pct: null }]) {
    request.mock.mockImplementation(async () => Response.json(response));
    assert.deepEqual(await getPortfolioAllocation(id), response);
  }
  for (const bad of [{ portfolio_id: other }, { cash: 400 }, { cash_weight_pct: "101" }, { hhi: "-0.1" }, { hhi: "1.1" }, { assets: [allocation.assets[0], allocation.assets[0]] }, { status: "estimated" }, { assets: [{ ...allocation.assets[0], weight_pct: null }] }, { stale_symbols: ["UNKNOWN"] }]) {
    request.mock.mockImplementation(async () => Response.json({ ...allocation, ...bad }));
    await assert.rejects(getPortfolioAllocation(id), /incompatible|inconsistent/);
  }
});

test("allocation rejects invalid IDs before requesting and hides provider diagnostics", async (t) => {
  const request = t.mock.method(globalThis, "fetch", async () => new Response("private diagnostics", { status: 503 }));
  await assert.rejects(getPortfolioAllocation("bad"), /valid portfolio/);
  assert.equal(request.mock.callCount(), 0);
  await assert.rejects(getPortfolioAllocation(id), (error) => error.statusCode === 503 && !error.message.includes("private"));
});

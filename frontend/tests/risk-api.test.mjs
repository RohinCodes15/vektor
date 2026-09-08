import { test } from "node:test";
import assert from "node:assert/strict";
import { getPortfolioRisk } from "../src/lib/api.ts";
import { id, other, risk, unavailableRisk } from "./allocation-fixtures.mjs";

test("risk uses the read-only API and preserves signed contributions", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.pathname, `/api/v1/portfolios/${id}/risk`);
    assert.equal(options.method, "GET"); assert.equal(options.cache, "no-store"); assert.equal(options.credentials, "omit");
    return Response.json(risk);
  });
  assert.deepEqual(await getPortfolioRisk(id), risk);
});

test("risk preserves signed contributions and unavailable states; rejects unsafe responses", async (t) => {
  const request = t.mock.method(globalThis, "fetch", async () => Response.json(unavailableRisk));
  assert.deepEqual(await getPortfolioRisk(id), unavailableRisk);
  const zero = { ...risk, portfolio_volatility_pct: "0.0000", assets: risk.assets.map((asset) => ({ ...asset, volatility_contribution_pct: null, contribution_share_pct: null })), correlations: [{ symbol_a: "AAPL", symbol_b: "MSFT", correlation: null }] };
  request.mock.mockImplementation(async () => Response.json(zero)); assert.deepEqual(await getPortfolioRisk(id), zero);
  for (const bad of [{ portfolio_id: other }, { observations: -1 }, { observations: 5 }, { portfolio_volatility_pct: "NaN" }, { portfolio_volatility_pct: "-1" }, { correlations: [{ symbol_a: "AAPL", symbol_b: "MSFT", correlation: "1.01" }] }, { correlations: [{ symbol_a: "UNKNOWN", symbol_b: "MSFT", correlation: "0.1" }] }, { assets: [{ ...risk.assets[0], contribution_share_pct: 100 }] }]) {
    request.mock.mockImplementation(async () => Response.json({ ...risk, ...bad }));
    await assert.rejects(getPortfolioRisk(id), /incompatible portfolio risk/);
  }
  const calls = request.mock.callCount();
  await assert.rejects(getPortfolioRisk("bad"), /valid portfolio/);
  assert.equal(request.mock.callCount(), calls);
  for (const get of [getPortfolioRisk]) {
    request.mock.mockImplementation(async () => new Response("private diagnostics", { status: 503 }));
    await assert.rejects(get(id), (error) => error.statusCode === 503 && !error.message.includes("private"));
  }
});

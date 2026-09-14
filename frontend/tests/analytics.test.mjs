import { test } from "node:test";
import assert from "node:assert/strict";
import { getPortfolioAnalytics, getPortfolioEquityHistory } from "../src/lib/api.ts";

const id = "00000000-0000-4000-8000-000000000001";
const other = "00000000-0000-4000-8000-000000000002";
const snapshot = (taken_at, equity = "1000.00", snapshotId = id) => ({ id: snapshotId, portfolio_id: id, taken_at, cash: equity, positions_value: "0.00", equity, net_deposits: "1000.00", realized_pnl: "0.00", unrealized_pnl: "0.00", prices_as_of: null });
const history = [snapshot("2026-01-01T00:00:00Z"), snapshot("2026-11-06T00:00:00Z", "1010.00", other)];
const metrics = { portfolio_id: id, currency: "USD", as_of: "2026-11-06T00:00:00Z", snapshots: 2, daily_observations: 2, equity: "1010.00", net_deposits: "1000.00", realized_pnl: "0.00", unrealized_pnl: "10.00", total_return_pct: "1.0000", latest_daily_return_pct: "1.0000", volatility_pct: null, max_drawdown_pct: "0.0000", sharpe_ratio: null };
const empty = { ...metrics, as_of: null, snapshots: 0, daily_observations: 0, equity: null, net_deposits: null, realized_pnl: null, unrealized_pnl: null, total_return_pct: null, latest_daily_return_pct: null, max_drawdown_pct: null };

test("analytics use read-only endpoints and preserve exact metrics and recorded snapshots", async (t) => {
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push(url.pathname);
    assert.equal(options.method, "GET"); assert.equal(options.credentials, "omit"); assert.equal(options.cache, "no-store");
    return Response.json(url.pathname.endsWith("/analytics") ? metrics : history);
  });
  assert.deepEqual(await getPortfolioAnalytics(id), metrics);
  assert.deepEqual(await getPortfolioEquityHistory(id), history);
  assert.deepEqual(requests, [`/api/v1/portfolios/${id}/analytics`, `/api/v1/portfolios/${id}/equity-history`]);
});

test("analytics accept missing/insufficient data and reject wrong IDs, numbers and unsupported responses", async (t) => {
  const request = t.mock.method(globalThis, "fetch", async () => Response.json(empty));
  assert.deepEqual(await getPortfolioAnalytics(id), empty);
  for (const bad of [{ portfolio_id: other }, { snapshots: -1 }, { daily_observations: 3 }, { total_return_pct: 1 }, { sharpe_ratio: "Infinity" }, { volatility_pct: "-1" }, { max_drawdown_pct: "1" }, { as_of: "bad" }, { currency: "EUR" }]) {
    request.mock.mockImplementation(async () => Response.json({ ...metrics, ...bad }));
    await assert.rejects(getPortfolioAnalytics(id), /incompatible portfolio analytics/);
  }
  for (const bad of [[...history].reverse(), [history[0], history[0]], [{ ...history[0], portfolio_id: other }], [{ ...history[0], equity: 1000 }], [{ ...history[0], equity: "NaN" }], [{ ...history[0], prices_as_of: "2026-02-30" }]]) {
    request.mock.mockImplementation(async () => Response.json(bad));
    await assert.rejects(getPortfolioEquityHistory(id), /incompatible recorded equity/);
  }
  request.mock.mockImplementation(async () => Response.json([]));
  assert.deepEqual(await getPortfolioEquityHistory(id), []);
  const count = request.mock.callCount();
  await assert.rejects(getPortfolioAnalytics("bad"), /valid portfolio/);
  await assert.rejects(getPortfolioEquityHistory("bad"), /valid portfolio/);
  assert.equal(request.mock.callCount(), count);
});

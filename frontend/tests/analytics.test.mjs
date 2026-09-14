import { test } from "node:test";
import assert from "node:assert/strict";
import { getPortfolioAnalytics, getPortfolioEquityHistory } from "../src/lib/api.ts";
import { historyRange } from "../src/lib/history-range.ts";
import { mount, nodes } from "./component-runtime.mjs";

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

const settle = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };
const text = (tree) => JSON.stringify(tree, (_key, value) => typeof value === "function" ? undefined : value);
const ui = { Badge: "badge", Button: "button", MetricCard: "metric", Panel: "panel" };
async function performance(api) {
  return mount("../src/components/portfolio-performance.tsx", { "../lib/api": api, "../lib/history-range": { historyRange }, "./equity-chart": { EquityChart: "chart" }, "./ui": ui }, "PortfolioPerformance", { id });
}

test("cards display backend metrics without deriving null values; ranges filter only chart observations", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-11-06T00:00:00Z") });
  let calls = 0;
  const app = await performance({ getPortfolioAnalytics: async () => { calls++; return metrics; }, getPortfolioEquityHistory: async () => history });
  let tree = app.render(); assert.match(text(tree), /Loading recorded equity/);
  app.flush(); await settle(); tree = app.render();
  const values = () => nodes(tree).filter((node) => node.type === "metric").map((node) => node.props.value);
  assert.deepEqual(values(), ["1.0000%", "1.0000%", "Unavailable", "0.0000%", "Unavailable"]);
  nodes(tree).find((node) => node.type === "button" && node.props.children === "1M").props.onClick(); tree = app.render(); app.flush();
  assert.equal(nodes(tree).find((node) => node.type === "chart").props.snapshots.length, 1);
  assert.deepEqual(values(), ["1.0000%", "1.0000%", "Unavailable", "0.0000%", "Unavailable"]);
  assert.equal(calls, 1);
  app.unmount();
});

test("empty history, empty ranges, and failed requests offer honest states and retries", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-11-06T00:00:00Z") });
  let fail = true;
  let snapshots = [];
  const app = await performance({ getPortfolioAnalytics: async () => { if (fail) throw new Error("Offline"); return empty; }, getPortfolioEquityHistory: async () => snapshots });
  let tree = app.render(); app.flush(); await settle(); tree = app.render();
  assert.match(text(tree), /Offline/);
  fail = false;
  nodes(tree).find((node) => node.type === "button").props.onClick(); tree = app.render();
  assert.match(text(tree), /Loading recorded equity/);
  app.flush(); await settle(); tree = app.render(); assert.match(text(tree), /No equity snapshots recorded/);
  assert.ok(nodes(tree).filter((node) => node.type === "metric").every((node) => node.props.value === "Unavailable"));
  snapshots = [history[0]];
  nodes(tree).find((node) => node.type === "button" && node.props.children === "Refresh performance").props.onClick(); app.render(); app.flush(); await settle(); tree = app.render();
  nodes(tree).find((node) => node.type === "button" && node.props.children === "1M").props.onClick(); tree = app.render();
  assert.match(text(tree), /No snapshots in this range/);
  assert.equal(nodes(tree).some((node) => node.type === "chart"), false);
  app.unmount();
});

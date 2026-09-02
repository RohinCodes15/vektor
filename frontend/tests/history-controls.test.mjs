import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { ApiError } from "../src/lib/api.ts";
import * as chartGeometry from "../src/lib/price-chart.ts";
import { historyRange } from "../src/lib/history-range.ts";

const query = { symbol: "AAPL", start: "2024-01-01", end: "2024-02-01" };

test("history hook loads, ignores late responses, handles errors/empty data, and retries", async () => {
  const requests = [];
  const app = await mount("../src/hooks/use-market-history.ts", {
    "../lib/api": { ApiError, getMarketHistory: (query, signal) => new Promise((resolve, reject) => requests.push({ query, signal, resolve, reject })) },
  }, "useMarketHistory");
  let hook = app.render(); app.flush();
  assert.equal(hook.state.status, "idle");
  const first = hook.load(query); await Promise.resolve();
  assert.deepEqual(app.render().state, { status: "loading", query });
  const second = hook.load({ ...query, symbol: "MSFT" }); await Promise.resolve();
  assert.equal(requests[0].signal.aborted, true);
  requests[1].resolve({ symbol: "MSFT", bars: [] }); await second;
  assert.deepEqual(app.render().state, { status: "success", data: { symbol: "MSFT", bars: [] } });
  requests[0].resolve({ symbol: "AAPL", bars: [1] }); await first;
  assert.equal(app.render().state.data.symbol, "MSFT");
  for (const status of [404, 503]) {
    const attempt = hook.load(query); await Promise.resolve();
    requests.at(-1).reject(new ApiError("Unavailable", status)); await attempt;
    assert.equal(app.render().state.statusCode, status);
  }
  const retry = hook.load(query); await Promise.resolve();
  requests.at(-1).resolve({ symbol: "AAPL", bars: [] }); await retry;
  assert.equal(app.render().state.status, "success");
  app.unmount();
  assert.equal(requests.at(-1).signal.aborted, true);
});

test("same-turn rapid symbol changes and Strict Mode cleanup avoid obsolete requests", async () => {
  const requests = [];
  const app = await mount("../src/hooks/use-market-history.ts", {
    "../lib/api": { ApiError, getMarketHistory: async (query) => { requests.push(query); return { symbol: query.symbol, bars: [] }; } },
  }, "useMarketHistory");
  const hook = app.render(); app.flush();
  await Promise.all([hook.load(query), hook.load({ ...query, symbol: "MSFT" }), hook.load({ ...query, symbol: "NVDA" })]);
  assert.deepEqual(requests.map(({ symbol }) => symbol), ["NVDA"]);
  const pending = hook.load(query); app.unmount(); await pending;
  assert.equal(requests.length, 1);
});


test("range controls deduplicate requests, preserve range across symbols, and hide stale charts", async () => {
  const requests = [];
  let state = { status: "idle" };
  const load = (query) => { requests.push(query); };
  const app = await mount("../src/components/stock-history.tsx", {
    "../hooks/use-market-history": { useMarketHistory: () => ({ state, load }) },
    "../lib/history-range": { historyRange },
    "./price-chart": { PriceChart: "chart" },
    "./ui": { Button: "button", Field: "field" },
  }, "StockHistory", { symbol: "AAPL" });
  let tree = app.render(); app.flush();
  const click = (label) => nodes(tree).find((node) => node.type === "button" && node.props.children === label).props.onClick();
  click("1Y"); tree = app.render(); app.flush();
  assert.equal(requests.length, 1);
  click("1M"); tree = app.render(); app.flush();
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[1], { symbol: "AAPL", ...historyRange("1M") });
  state = { status: "success", data: { ...requests[1], bars: [{}] } };
  tree = app.render();
  assert.equal(nodes(tree).filter((node) => node.type === "chart").length, 1);
  tree = app.render({ symbol: "MSFT" });
  assert.equal(nodes(tree).filter((node) => node.type === "chart").length, 0);
  app.flush();
  assert.deepEqual(requests.at(-1), { ...requests[1], symbol: "MSFT" });
  for (const next of [{ status: "loading" }, { status: "error", statusCode: 404 }, { status: "success", data: { ...requests.at(-1), bars: [] } }, { status: "error", statusCode: 503, message: "Provider unavailable" }]) {
    state = next; tree = app.render({ symbol: "MSFT" });
    assert.equal(nodes(tree).filter((node) => node.type === "chart").length, 0);
    assert.equal(nodes(tree).some((node) => node.props?.role === "alert"), next.statusCode === 503);
  }
});


test("chart tooltip stays inside narrow viewports and keyboard selection matches the observation", async (t) => {
  let resize;
  const previousObserver = globalThis.ResizeObserver;
  t.after(() => { if (previousObserver) globalThis.ResizeObserver = previousObserver; else delete globalThis.ResizeObserver; });
  globalThis.ResizeObserver = class {
    constructor(callback) { resize = callback; }
    observe() {}
    disconnect() {}
  };
  const history = { symbol: "AAPL", currency: "USD", cached: false, fetched_at: "2024-01-03T00:00:00Z", bars: [{ date: "2024-01-01", close: 100 }, { date: "2024-01-02", close: 110 }] };
  const app = await mount("../src/components/price-chart.tsx", { "../lib/price-chart": chartGeometry }, "PriceChart", { history });
  let tree = app.render();
  tree.props.ref.current = {};
  app.flush();
  resize([{ contentRect: { width: 160 } }]);
  tree = app.render();
  const slider = nodes(tree).find((node) => node.type === "input");
  slider.props.onChange({ target: { value: "0" } });
  tree = app.render();
  assert.match(nodes(tree).find((node) => node.type === "input").props["aria-valuetext"], /2024-01-01, close 100 USD/);
  const tooltip = nodes(tree).find((node) => node.type === "g" && node.props.transform);
  const x = Number(tooltip.props.transform.match(/translate\(([^,]+)/)[1]);
  assert.ok(x >= 0 && x + 140 <= 160);
  nodes(tree).find((node) => node.type === "svg").props.onPointerCancel();
  tree = app.render();
  assert.equal(nodes(tree).some((node) => node.props?.className === "chart-crosshair"), false);
  app.unmount();
});

test("ticker search validates, normalizes, and clears errors on edits", async () => {
  const { normalizeMarketSymbol } = await import("../src/lib/api.ts");
  const app = await mount("../src/components/market-workspace.tsx", {
    "motion/react": { motion: { div: "div" }, useReducedMotion: () => true },
    "../lib/api": { normalizeMarketSymbol },
    "./stock-history": { StockHistory: "history" },
    "./ui": { Badge: "badge", Button: "button", Field: "field", Panel: "panel" },
  }, "MarketWorkspace");
  let tree = app.render();
  const field = () => nodes(tree).find((node) => node.type === "field");
  const submit = () => nodes(tree).find((node) => node.type === "form").props.onSubmit({ preventDefault() {} });
  field().props.onChange({ target: { value: "AAPL?" } }); tree = app.render();
  submit(); tree = app.render();
  assert.equal(field().props["aria-invalid"], true);
  assert.equal(nodes(tree).find((node) => node.type === "history").props.symbol, "AAPL");
  field().props.onChange({ target: { value: " brk-b " } }); tree = app.render();
  assert.equal(field().props["aria-invalid"], false);
  submit(); tree = app.render();
  assert.equal(nodes(tree).find((node) => node.type === "history").props.symbol, "BRK-B");
});

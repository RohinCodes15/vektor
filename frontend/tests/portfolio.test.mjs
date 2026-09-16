import { test } from "node:test";
import assert from "node:assert/strict";
import { getPortfolios, getPortfolioHoldings } from "../src/lib/api.ts";
import { formatMoney, formatTotalPnl, moneyInCents } from "../src/lib/portfolio-values.ts";
import { mount, nodes } from "./component-runtime.mjs";

const id = "00000000-0000-4000-8000-000000000001";
const other = "00000000-0000-4000-8000-000000000002";
const portfolio = { id, name: "Research", mode: "paper", currency: "USD", starting_cash: "1000.00", cash: "900.00", realized_pnl: "0.00", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" };
const holding = { symbol: "AAPL", quantity: "1", cost_basis: "100.00", last_price: "110.0000", price_date: "2026-11-05", market_value: "110.00", unrealized_pnl: "10.00", allocation_pct: "10.89" };
const valuation = { portfolio_id: id, currency: "USD", cash: "900.00", positions_value: "110.00", equity: "1010.00", unrealized_pnl: "10.00", realized_pnl: "0.00", cash_allocation_pct: "89.11", valued_at: "2026-11-06T00:00:00Z", holdings: [holding] };
const unpriced = { ...valuation, positions_value: null, equity: null, unrealized_pnl: null, cash_allocation_pct: null, holdings: [{ ...holding, last_price: null, price_date: null, market_value: null, unrealized_pnl: null, allocation_pct: null }] };

test("portfolio reads use existing endpoints and preserve decimal strings and unpriced nulls", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(options.method, "GET");
    assert.equal(options.credentials, "omit");
    assert.equal(options.cache, "no-store");
    if (url.pathname === "/api/v1/portfolios") return Response.json([portfolio]);
    assert.equal(url.pathname, `/api/v1/portfolios/${id}/holdings`);
    return Response.json(unpriced);
  });
  assert.deepEqual(await getPortfolios(), [portfolio]);
  assert.deepEqual(await getPortfolioHoldings(id), unpriced);
});

test("portfolio boundary rejects incompatible balances and mismatched valuations", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const bad of [[{ ...portfolio, mode: "live" }], [{ ...portfolio, cash: 900 }], [{ ...portfolio, cash: "NaN" }], [{ ...portfolio, cash: "1.001" }], [{ ...portfolio, currency: "EUR" }], [portfolio, portfolio], {}]) {
    request.mock.mockImplementation(async () => Response.json(bad));
    await assert.rejects(getPortfolios(), /incompatible/);
  }
  for (const bad of [{ ...valuation, portfolio_id: other }, { ...valuation, cash: "-1" }, { ...valuation, holdings: [{ ...holding, quantity: "0" }] }, { ...valuation, equity: null }, { ...unpriced, equity: "900.00" }, { ...valuation, holdings: [{ ...holding, market_value: 110 }] }]) {
    request.mock.mockImplementation(async () => Response.json(bad));
    await assert.rejects(getPortfolioHoldings(id), /incompatible|inconsistent/);
  }
  const before = request.mock.callCount();
  await assert.rejects(getPortfolioHoldings("../orders"), /valid portfolio/);
  assert.equal(request.mock.callCount(), before);
});

test("portfolio errors use safe messages and cash-only responses are accepted", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const status of [404, 502, 503, 500]) {
    request.mock.mockImplementation(async () => new Response("private diagnostics", { status }));
    await assert.rejects(getPortfolioHoldings(id), (error) => error.statusCode === status && !error.message.includes("private"));
  }
  const cashOnly = { ...valuation, positions_value: "0.00", equity: "900.00", unrealized_pnl: "0.00", cash_allocation_pct: "100.00", holdings: [] };
  request.mock.mockImplementation(async () => Response.json(cashOnly));
  assert.deepEqual(await getPortfolioHoldings(id), cashOnly);
});

test("money display and total P&L stay exact, including large values and nulls", () => {
  assert.equal(formatMoney("9007199254740993.01"), "$9,007,199,254,740,993.01");
  assert.equal(formatMoney("-0.01"), "−$0.01");
  assert.equal(formatMoney("0E-2"), "$0.00");
  assert.equal(formatTotalPnl("0.10", "0.20"), "$0.30");
  assert.equal(formatTotalPnl("10.10", "-20.20"), "−$10.10");
  assert.equal(formatTotalPnl("10.00", null), "Unavailable");
  assert.equal(formatMoney(null), "Unavailable");
  assert.throws(() => moneyInCents("1.001"));
});

const ui = { Badge: "badge", Button: "button", MetricCard: "metric", Panel: "panel" };
const text = (tree) => JSON.stringify(tree, (_key, value) => typeof value === "function" ? undefined : value);
const settle = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

test("portfolio list loads, selects existing portfolios, handles empty lists, errors, and retries", async () => {
  let response = [portfolio, { ...portfolio, id: other, name: "Second" }];
  let fail = false;
  const app = await mount("../src/components/portfolio-dashboard.tsx", {
    "../lib/api": { getPortfolios: async () => { if (fail) throw new Error("Offline"); return response; } },
    "../lib/portfolio-values": { formatMoney, formatTotalPnl }, "./transaction-history": { TransactionHistory: "transactions" }, "./ui": ui,
  }, "PortfolioDashboard");
  let tree = app.render(); assert.match(text(tree), /Loading paper portfolios/);
  app.flush(); await settle(); tree = app.render();
  const selector = nodes(tree).find((node) => node.type === "select");
  assert.equal(selector.props.value, id);
  selector.props.onChange({ target: { value: other } }); tree = app.render();
  assert.equal(nodes(tree).find((node) => node.type === "select").props.value, other);
  const refresh = () => nodes(tree).find((node) => node.type === "button").props.onClick();
  fail = true; refresh(); tree = app.render(); app.flush(); await settle(); tree = app.render();
  assert.match(text(tree), /Offline/);
  fail = false; response = []; refresh(); tree = app.render(); app.flush(); await settle(); tree = app.render();
  assert.match(text(tree), /No paper portfolios yet/);
  assert.equal(nodes(tree).some((node) => node.type === "metric"), false);
  app.unmount();
});

test("portfolio details show real metrics, unpriced warnings, errors and empty holdings", async () => {
  let response = valuation;
  let fail = false;
  const imports = {
    "../lib/api": { getPortfolioHoldings: async () => { if (fail) throw new Error("Provider unavailable"); return response; } },
    "../lib/portfolio-values": { formatMoney, formatTotalPnl }, "./transaction-history": { TransactionHistory: "transactions" }, "./ui": ui,
  };
  for (const scenario of [valuation, unpriced, { ...valuation, holdings: [], equity: "900.00", unrealized_pnl: "0.00" }, null]) {
    response = scenario; fail = scenario === null;
    const app = await mount("../src/components/portfolio-dashboard.tsx", imports, "PortfolioDetails", { id });
    let tree = app.render();
    assert.match(text(tree), /Loading portfolio valuation/);
    assert.ok(nodes(tree).filter((node) => node.type === "metric").every((node) => node.props.value === "—"));
    app.flush(); await settle(); tree = app.render();
    if (scenario === valuation) {
      assert.equal(nodes(tree).find((node) => node.type === "metric" && node.props.label === "Portfolio value").props.value, "$1,010.00");
      assert.match(text(tree), /AAPL/);
    } else if (scenario === unpriced) assert.match(text(tree), /Some holdings have no recent price/);
    else if (scenario) assert.match(text(tree), /No open holdings/);
    else {
      assert.match(text(tree), /Provider unavailable/);
      fail = false; response = valuation;
      nodes(tree).find((node) => node.type === "button").props.onClick();
      app.render(); app.flush(); await settle(); tree = app.render();
      assert.match(text(tree), /AAPL/);
    }
    app.unmount();
  }
});

test("leaving a portfolio aborts its valuation and ignores a late response", async () => {
  let resolve;
  let signal;
  const app = await mount("../src/components/portfolio-dashboard.tsx", {
    "../lib/api": { getPortfolioHoldings: (_id, pending) => { signal = pending; return new Promise((done) => { resolve = done; }); } },
    "../lib/portfolio-values": { formatMoney, formatTotalPnl }, "./transaction-history": { TransactionHistory: "transactions" }, "./ui": ui,
  }, "PortfolioDetails", { id });
  app.render(); app.flush(); await settle();
  app.unmount();
  assert.equal(signal.aborted, true);
  resolve(valuation); await settle();
  assert.match(text(app.render()), /Loading portfolio valuation/);
});

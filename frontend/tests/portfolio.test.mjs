import { test } from "node:test";
import assert from "node:assert/strict";
import { getPortfolios, getPortfolioHoldings } from "../src/lib/api.ts";
import { formatMoney, formatTotalPnl, moneyInCents } from "../src/lib/portfolio-values.ts";

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

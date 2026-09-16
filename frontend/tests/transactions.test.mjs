import { test } from "node:test";
import assert from "node:assert/strict";
import { getPortfolioTransactions } from "../src/lib/api.ts";

const id = "00000000-0000-4000-8000-000000000001";
const trade = { id: "00000000-0000-4000-8000-000000000002", portfolio_id: id, client_order_id: "test-1", symbol: "AAPL", side: "buy", quantity: "0.123456", price: "100.1234", price_date: "2026-11-05", notional: "12.36", realized_pnl: null, executed_at: "2026-11-06T12:30:00Z" };

test("transactions use the portfolio endpoint and preserve exact quantity, price, total and dates", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.pathname, `/api/v1/portfolios/${id}/transactions`);
    assert.equal(options.method, "GET"); assert.equal(options.cache, "no-store");
    assert.equal(options.credentials, "omit");
    return Response.json([trade]);
  });
  assert.deepEqual(await getPortfolioTransactions(id), [trade]);
});

test("transaction boundary rejects bad IDs, duplicate trades and incompatible financial values", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  await assert.rejects(getPortfolioTransactions("bad"), /valid portfolio/);
  assert.equal(request.mock.callCount(), 0);
  for (const data of [{}, [trade, trade], ...[{ portfolio_id: trade.id }, { side: "short" }, { quantity: 1 }, { price: "NaN" }, { quantity: "0" }, { notional: "1.001" }, { price_date: "2026-02-30" }, { executed_at: "2026-11-06T12:30:00" }, { side: "sell", realized_pnl: null }].map((bad) => [{ ...trade, ...bad }])]) {
    request.mock.mockImplementation(async () => Response.json(data));
    await assert.rejects(getPortfolioTransactions(id), /incompatible paper transactions/);
  }
  request.mock.mockImplementation(async () => Response.json([]));
  assert.deepEqual(await getPortfolioTransactions(id), []);
  request.mock.mockImplementation(async () => new Response("private error", { status: 503 }));
  await assert.rejects(getPortfolioTransactions(id), /provider is unavailable/);
});

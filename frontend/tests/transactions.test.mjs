import { test } from "node:test";
import assert from "node:assert/strict";
import { getPortfolioTransactions } from "../src/lib/api.ts";
import { formatMoney } from "../src/lib/portfolio-values.ts";
import { mount, nodes } from "./component-runtime.mjs";

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

const settle = async () => { for (let index = 0; index < 8; index++) await Promise.resolve(); };
const text = (tree) => JSON.stringify(tree, (_key, value) => typeof value === "function" ? undefined : value);

function browser(t) {
  const priorWindow = globalThis.window;
  const priorDocument = globalThis.document;
  const listeners = new EventTarget();
  const documentListeners = new EventTarget();
  let tick;
  globalThis.document = { visibilityState: "visible", addEventListener: documentListeners.addEventListener.bind(documentListeners), removeEventListener: documentListeners.removeEventListener.bind(documentListeners) };
  globalThis.window = { setInterval: (callback, delay) => { assert.equal(delay, 15000); tick = callback; return 1; }, clearInterval() {}, addEventListener: listeners.addEventListener.bind(listeners), removeEventListener: listeners.removeEventListener.bind(listeners) };
  t.after(() => { if (priorWindow) globalThis.window = priorWindow; else delete globalThis.window; if (priorDocument) globalThis.document = priorDocument; else delete globalThis.document; });
  return { tick: () => tick(), focus: () => listeners.dispatchEvent(new Event("focus")), visible: () => documentListeners.dispatchEvent(new Event("visibilitychange")) };
}

async function history(getPortfolioTransactions, onTrades = () => {}) {
  return mount("../src/components/transaction-history.tsx", {
    "../lib/api": { getPortfolioTransactions }, "../lib/portfolio-values": { formatMoney },
    "./ui": { Badge: "badge", Button: "button", Panel: "panel" },
  }, "TransactionHistory", { id, onTrades });
}

test("history renders loading, empty, error, retry and exact paper trade columns", async (t) => {
  browser(t);
  let result = [];
  let error = false;
  const app = await history(async () => { if (error) throw new Error("Offline"); return result; });
  let tree = app.render(); assert.match(text(tree), /Loading paper trades/);
  app.flush(); await settle(); tree = app.render(); assert.match(text(tree), /No paper trades yet/);
  result = [trade, { ...trade, id: "sell-2", side: "sell", realized_pnl: "1.00" }];
  const refresh = () => nodes(tree).find((node) => node.type === "button").props.onClick();
  refresh(); app.render(); app.flush(); await settle(); tree = app.render();
  for (const value of ["Ticker", "Side", "Quantity", "Execution price", "Total", "Executed (UTC)", "AAPL", "Buy", "Sell", "100.1234", "0.123456", "$12.36", "2026-11-06 12:30:00 UTC"]) assert.ok(text(tree).includes(value), value);
  assert.ok(nodes(tree).some((node) => node.props?.role === "region" && node.props.tabIndex === 0));
  error = true; refresh(); app.render(); app.flush(); await settle(); tree = app.render();
  assert.match(text(tree), /Offline/);
  assert.equal(nodes(tree).some((node) => node.type === "table"), false);
  error = false; refresh(); app.render(); app.flush(); await settle(); tree = app.render();
  assert.match(text(tree), /AAPL/);
  app.unmount();
});

test("new trades refresh balances after polling, focus and manual refresh; hidden tabs do not poll", async (t) => {
  const view = browser(t);
  let result = [];
  let calls = 0;
  let updates = 0;
  const app = await history(async () => { calls++; return result; }, () => updates++);
  app.render(); app.flush(); await settle();
  result = [trade]; view.tick(); await settle(); assert.equal(updates, 1);
  view.focus(); await settle(); assert.equal(updates, 1);
  globalThis.document.visibilityState = "hidden";
  const before = calls; view.tick(); await settle(); assert.equal(calls, before);
  globalThis.document.visibilityState = "visible";
  result = [...result, { ...trade, id: "new-trade" }];
  view.visible(); await settle(); assert.equal(updates, 2);
  const tree = app.render(); nodes(tree).find((node) => node.type === "button").props.onClick();
  app.render(); app.flush(); await settle(); assert.equal(updates, 2);
  app.unmount(); view.focus(); view.visible(); await settle(); assert.equal(updates, 2);
});

test("history aborts on portfolio switch and ignores late results", async (t) => {
  browser(t);
  let finish;
  let signal;
  const app = await history((_id, pending) => { signal = pending; return new Promise((resolve) => { finish = resolve; }); });
  app.render(); app.flush(); await settle(); app.unmount();
  assert.equal(signal.aborted, true);
  finish([trade]); await settle();
  assert.doesNotMatch(text(app.render()), /AAPL/);
});

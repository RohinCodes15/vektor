import { test } from "node:test";
import assert from "node:assert/strict";
import { getMarketHistory } from "../src/lib/api.ts";

const query = { symbol: "AAPL", start: "2024-01-02", end: "2024-01-03" };
const bar = { date: "2024-01-02", open: 100, high: 110, low: 90, close: 105, adjusted_close: 52.5, volume: 1000 };
const history = { ...query, interval: "1d", currency: "USD", source: "yahoo_finance", cached: false, fetched_at: "2024-01-04T09:30:00.123456+00:00", bars: [bar, { ...bar, date: "2024-01-03" }] };

test("history encodes inclusive dates and daily interval, normalizes symbols, and preserves provider data", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.pathname, "/api/v1/market/history");
    assert.deepEqual(Object.fromEntries(url.searchParams), { ...query, interval: "1d" });
    assert.equal(options.method, "GET");
    assert.equal(options.cache, "no-store");
    assert.equal(options.credentials, "omit");
    assert.equal(options.redirect, "error");
    return Response.json(history);
  });
  assert.deepEqual(await getMarketHistory({ ...query, symbol: " aapl " }), history);
});

test("Yahoo-style symbols are encoded safely", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const symbol of ["^GSPC", "BRK-B", "BRK.B", "7203.T", "EURUSD=X", "GC=F"]) {
    request.mock.mockImplementation(async (url) => {
      assert.equal(url.searchParams.get("symbol"), symbol);
      assert.equal([...url.searchParams.keys()].length, 4);
      return Response.json({ ...history, symbol });
    });
    assert.equal((await getMarketHistory({ ...query, symbol })).symbol, symbol);
  }
});

test("invalid query input fails before a request", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const invalid of [
    { symbol: "" }, { symbol: "AAPL&token=x" }, { symbol: "A".repeat(16) },
    { start: "2024-02-30" }, { start: "0000-01-01" }, { start: "2024-1-02" },
    { end: "2024-01-01" }, { end: "not-a-date" },
    { start: "9999-01-01", end: "9999-01-02" }, { interval: "1h" },
  ]) await assert.rejects(getMarketHistory({ ...query, ...invalid }));
  assert.equal(request.mock.callCount(), 0);
});

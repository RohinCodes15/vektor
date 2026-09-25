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

test("same-day ranges, null currency, empty bars, and cached history are valid", async (t) => {
  const response = { ...history, end: query.start, currency: null, cached: true, bars: [] };
  t.mock.method(globalThis, "fetch", async () => Response.json(response));
  assert.deepEqual(await getMarketHistory({ ...query, end: query.start }), response);
});

test("history validates metadata and matches the requested symbol and dates", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const invalid of [
    null, [], {}, { ...history, symbol: "MSFT" }, { ...history, interval: "1h" },
    { ...history, start: "2024-01-01" }, { ...history, end: "2024-01-04" },
    { ...history, currency: 1 }, { ...history, source: "synthetic" },
    { ...history, cached: "false" }, { ...history, fetched_at: "2024-01-04T09:30:00" },
    { ...history, fetched_at: "2024-02-30T09:30:00Z" },
    { ...history, fetched_at: "2024-01-04T24:00:00Z" },
    { ...history, bars: {} }, { ...history, extra: true },
  ]) {
    request.mock.mockImplementation(async () => Response.json(invalid));
    await assert.rejects(getMarketHistory(query), /incompatible market history response/);
  }
});

test("invalid, unordered, duplicate, or out-of-range bars are rejected, never repaired", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const bars of [
    [null], [{ ...bar, open: 0 }], [{ ...bar, adjusted_close: -1 }],
    [{ ...bar, high: 99 }], [{ ...bar, low: 101 }], [{ ...bar, close: "105" }],
    [{ ...bar, volume: -1 }], [{ ...bar, volume: 1.5 }], [{ ...bar, volume: Number.MAX_SAFE_INTEGER + 1 }],
    [{ ...bar, open: Infinity }], [{ ...bar, extra: true }], [{ ...bar, date: "2024-02-30" }],
    [{ ...bar, date: "2024-01-01" }], [{ ...bar, date: "2024-01-04" }],
    [bar, bar], [history.bars[1], bar],
  ]) {
    request.mock.mockImplementation(async () => Response.json({ ...history, bars }));
    await assert.rejects(getMarketHistory(query), /incompatible market history response/);
  }
});

test("known HTTP errors have actionable messages without exposing server bodies", async (t) => {
  const request = t.mock.method(globalThis, "fetch");
  for (const [status, message] of [[404, /No historical data/], [422, /query was rejected/], [502, /returned invalid data/], [503, /provider is unavailable/], [500, /HTTP 500/]]) {
    request.mock.mockImplementation(async () => new Response("private provider diagnostics", { status }));
    await assert.rejects(getMarketHistory(query), (error) => {
      assert.match(error.message, message);
      assert.equal(error.statusCode, status);
      return true;
    });
  }
});

test("history reuses network, JSON, timeout, and cancellation handling", async (t) => {
  const request = t.mock.method(globalThis, "fetch", async () => { throw new TypeError("network failure"); });
  await assert.rejects(getMarketHistory(query), /could not be reached/);
  request.mock.mockImplementation(async () => new Response("bad json"));
  await assert.rejects(getMarketHistory(query), /invalid market history response/);
  const timeout = t.mock.method(AbortSignal, "timeout", () => AbortSignal.abort(new DOMException("timeout", "TimeoutError")));
  request.mock.mockImplementation(async (_url, { signal }) => { throw signal.reason; });
  await assert.rejects(getMarketHistory(query), /market history request timed out/);
  timeout.mock.restore();
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(getMarketHistory(query, controller.signal), { name: "AbortError" });
});

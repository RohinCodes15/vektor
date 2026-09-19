import { test } from "node:test";
import assert from "node:assert/strict";
import { historyRange } from "../src/lib/history-range.ts";
import { normalizeMarketSymbol, getMarketHistory } from "../src/lib/api.ts";

test("ranges clamp UTC month ends and include all provider history", () => {
  for (const [range, start] of [["1M", "2024-02-29"], ["3M", "2023-12-31"], ["6M", "2023-09-30"], ["1Y", "2023-03-31"], ["ALL", "1900-01-01"]]) {
    assert.deepEqual(historyRange(range, new Date("2024-03-31T23:30:00Z")), { start, end: "2024-03-31" });
  }
  assert.equal(historyRange("1Y", new Date("2024-02-29T00:00:00Z")).start, "2023-02-28");
});

test("search validation and range queries reuse the market history API", async (t) => {
  const symbol = normalizeMarketSymbol(" brk-b ");
  assert.equal(symbol, "BRK-B");
  for (const invalid of ["", "  ", "AAPL?", "A".repeat(16)]) assert.throws(() => normalizeMarketSymbol(invalid), /valid market symbol/);
  t.mock.method(globalThis, "fetch", async (url) => {
    const query = Object.fromEntries(url.searchParams);
    assert.equal(query.symbol, symbol);
    return Response.json({ ...query, currency: null, source: "yahoo_finance", cached: false, fetched_at: "2024-04-01T00:00:00Z", bars: [] });
  });
  for (const range of ["1M", "3M", "6M", "1Y", "ALL"]) {
    const dates = historyRange(range, new Date("2024-03-31T00:00:00Z"));
    assert.equal((await getMarketHistory({ symbol, ...dates })).start, dates.start);
  }
});

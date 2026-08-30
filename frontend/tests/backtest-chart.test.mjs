import { test } from "node:test";
import assert from "node:assert/strict";
import { backtestChartGeometry, nearestBacktestPoint } from "../src/lib/backtest-chart.ts";

const values = [{ date: "2024-01-05", value: 10000 }, { date: "2024-01-08", value: 10100 }, { date: "2024-01-09", value: 9900 }];

test("backtest chart preserves returned dates and signed values", () => {
  const chart = backtestChartGeometry(values, 600);
  assert.deepEqual(chart.points.map(({ date, value }) => ({ date, value })), values);
  assert.equal(chart.points[1].x - chart.points[0].x, 3 * (chart.points[2].x - chart.points[1].x));
  assert.ok(chart.points[1].y < chart.points[0].y);
  assert.equal(chart.path.split("L").length, values.length);
});

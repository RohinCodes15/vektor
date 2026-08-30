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

test("drawdown geometry supports zero and negative values", () => {
  const chart = backtestChartGeometry([{ date: "2024-01-01", value: 0 }, { date: "2024-01-02", value: -12.5 }], 300);
  assert.ok(chart.zeroY !== null);
  assert.ok(chart.points[0].y < chart.points[1].y);
  assert.ok(!/NaN|Infinity/.test(chart.path));
  assert.equal(nearestBacktestPoint(chart.points, chart.points[1].x), 1);
});

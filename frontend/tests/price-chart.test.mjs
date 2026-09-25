import { test } from "node:test";
import assert from "node:assert/strict";
import { nearestChartPoint, priceChartGeometry, formatChartPrice } from "../src/lib/price-chart.ts";

// Numeric geometry inputs are test cases, never displayed as market data.
const observations = [{ date: "2024-01-05", close: 100 }, { date: "2024-01-08", close: 110 }, { date: "2024-01-09", close: 105 }];
test("chart uses actual close observations and calendar spacing without filling weekends", () => {
  const result = priceChartGeometry(observations, 600);
  assert.equal(result.points.length, observations.length);
  assert.equal(result.points[1].x - result.points[0].x, 3 * (result.points[2].x - result.points[1].x));
  assert.ok(result.points[1].y < result.points[0].y);
  assert.deepEqual(result.points.map(({ date, close }) => ({ date, close })), observations);
  assert.equal(result.path.split("L").length, observations.length);
});
test("empty, single-point, flat, tiny, and large prices produce finite geometry", () => {
  assert.equal(priceChartGeometry([], 240).path, "");
  for (const close of [100, Number.MIN_VALUE, Number.MAX_VALUE]) {
    for (const bars of [[{ date: "2024-01-05", close }], observations.map((bar) => ({ ...bar, close }))]) {
      const geometry = priceChartGeometry(bars, 240);
      assert.ok(!/NaN|Infinity/.test(geometry.path));
      for (const point of geometry.points) {
        assert.ok(point.x >= geometry.plot.left && point.x <= geometry.plot.right);
        assert.ok(point.y >= geometry.plot.top && point.y <= geometry.plot.bottom);
      }
      assert.ok(geometry.priceTicks.every(({ value, y }) => Number.isFinite(value) && Number.isFinite(y)));
    }
  }
});
test("nearest observation snaps correctly at gaps and endpoints", () => {
  const { points } = priceChartGeometry(observations, 600);
  assert.equal(nearestChartPoint([], 100), -1);
  assert.equal(nearestChartPoint(points, -100), 0);
  assert.equal(nearestChartPoint(points, 1000), 2);
  assert.equal(nearestChartPoint(points, points[1].x + 1), 1);
  assert.equal(nearestChartPoint(points, (points[0].x + points[1].x) / 2), 0);
});
test("mobile tick density stays readable and price labels stay bounded", () => {
  assert.equal(priceChartGeometry(observations, 240).dateTicks.length, 2);
  assert.equal(priceChartGeometry([observations[0]], 240).dateTicks.length, 1);
  for (const value of [0, 123.456, Number.MIN_VALUE, Number.MAX_VALUE]) assert.ok(formatChartPrice(value).length < 20);
});

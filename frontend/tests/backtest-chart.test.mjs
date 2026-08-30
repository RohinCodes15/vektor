import { test } from "node:test";
import assert from "node:assert/strict";
import { backtestChartGeometry, nearestBacktestPoint } from "../src/lib/backtest-chart.ts";
import { formatMoney } from "../src/lib/portfolio-values.ts";
import { mount, nodes } from "./component-runtime.mjs";

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

test("empty, single, flat, and narrow chart inputs remain finite", () => {
  assert.equal(backtestChartGeometry([], 200).path, "");
  for (const input of [[{ date: "2024-01-01", value: 0 }], [{ date: "2024-01-01", value: -2 }, { date: "2024-01-02", value: -2 }]]) {
    const chart = backtestChartGeometry(input, 200);
    assert.ok(!/NaN|Infinity/.test(chart.path));
    assert.ok(chart.points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)));
  }
  assert.equal(nearestBacktestPoint([], 0), -1);
});

test("chart slider exposes and selects each exact returned observation", async () => {
  const points = values.map(({ date, value }) => ({ date, equity: value.toFixed(2), drawdown_pct: value === 9900 ? "-2.0000" : "0", cash: "0.00", positions_value: value.toFixed(2) }));
  const component = await mount("../src/components/backtest-chart.tsx", {
    "../lib/api": {}, "../lib/backtest-chart": { backtestChartGeometry, nearestBacktestPoint }, "../lib/portfolio-values": { formatMoney },
  }, "BacktestChart", { points, kind: "drawdown" });
  let tree = component.render();
  const slider = nodes(tree).find((node) => node.props?.type === "range");
  assert.match(slider.props["aria-valuetext"], /2024-01-09.*-2\.0000%/);
  slider.props.onChange({ target: { value: "0" } });
  tree = component.render();
  assert.match(nodes(tree).find((node) => node.props?.type === "range").props["aria-valuetext"], /2024-01-05.*0%/);
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { comparisonChartGeometry, comparisonStrategyLabel } from "../src/lib/comparison-chart.ts";
import { nearestBacktestPoint } from "../src/lib/backtest-chart.ts";
import { formatMoney } from "../src/lib/portfolio-values.ts";

const dates = ["2024-01-05", "2024-01-08", "2024-01-09"];
const metrics = { total_return_pct: "2.0000", annualized_return_pct: null, sharpe_ratio: null, volatility_pct: "12.3456", max_drawdown_pct: "-1.2345", win_rate_pct: null, trades: 0 };
const data = {
  config: { symbol: "AAPL", start: "2024-01-01", end: "2024-01-31" }, dates, bars: 3, first_date: dates[0], last_date: dates[2],
  results: [
    { strategy: { kind: "buy_and_hold" }, status: "available", metrics, warnings: ["Sharpe needs more observations."], equity: ["10000.00", "10100.00", "10200.00"] },
    { strategy: { kind: "sma_crossover", fast_window: 2, slow_window: 3 }, status: "available", metrics: { ...metrics, trades: 2 }, warnings: [], equity: ["10000.00", "10150.00", "10200.00"] },
    { strategy: { kind: "rsi", period: 14, oversold: "30", overbought: "70" }, status: "unavailable", unavailable_reason: "Too few bars for warm-up.", metrics: null, warnings: [], equity: null },
  ],
  leaders: [{ metric: "total_return_pct", better: "higher", leaders: [0, 1], reason: null }, { metric: "sharpe_ratio", better: "higher", leaders: [], reason: "Insufficient observations." }],
  disclaimer: "Past paper results do not predict returns.",
};
function text(element) {
  if (Array.isArray(element)) return element.map(text).join("");
  if (element === null || element === undefined || typeof element === "boolean") return "";
  return typeof element === "object" ? text(element.props?.children) : String(element);
}
async function chart(input = data) {
  return mount("../src/components/comparison-chart.tsx", {
    "../lib/comparison-chart": { comparisonChartGeometry, comparisonStrategyLabel },
    "../lib/backtest-chart": { nearestBacktestPoint }, "../lib/portfolio-values": { formatMoney },
  }, "ComparisonChart", { data: input });
}

test("comparison geometry shares USD/date scales and preserves calendar gaps", () => {
  const geometry = comparisonChartGeometry(dates, data.results.map((result) => result.equity), 600);
  assert.equal(geometry.curves[0][0].y, geometry.curves[1][0].y);
  assert.equal(geometry.curves[0][2].y, geometry.curves[1][2].y);
  assert.equal(geometry.curves[0][1].x, geometry.curves[1][1].x);
  assert.equal(geometry.curves[0][1].x - geometry.curves[0][0].x, 3 * (geometry.curves[0][2].x - geometry.curves[0][1].x));
  assert.ok(geometry.curves[1][1].y < geometry.curves[0][1].y);
  assert.deepEqual(geometry.curves[0].map((point) => point.value), [10000, 10100, 10200]);
});

test("comparison geometry omits unequal or invalid arrays without padding or shifting", () => {
  for (const bad of [["10000.00"], ["10000.00", "NaN", "10200.00"], ["10000.00", "", "10200.00"]]) {
    const geometry = comparisonChartGeometry(dates, [data.results[0].equity, bad], 200);
    assert.equal(geometry.curves[1].length, 0);
    assert.equal(geometry.curves[0].length, 3);
    assert.equal(geometry.aligned[1], false);
  }
  assert.equal(comparisonChartGeometry([], [], 200).curves.length, 0);
  const flat = comparisonChartGeometry([dates[0]], [["0.00"], ["0.00"]], 160);
  assert.ok(flat.curves.flat().every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)));
});

test("comparison chart supports exact-value keyboard/pointer exploration and series toggles", async () => {
  const component = await chart();
  let tree = component.render();
  assert.match(text(tree), /\$10,200\.00/);
  const slider = nodes(tree).find((node) => node.props?.type === "range");
  slider.props.onChange({ target: { value: "1" } });
  tree = component.render();
  assert.match(text(tree), /\$10,100\.00/);
  assert.match(text(tree), /\$10,150\.00/);
  assert.equal(nodes(tree).find((node) => node.props?.type === "range").props["aria-valuetext"], dates[1]);
  const svg = nodes(tree).find((node) => node.type === "svg");
  svg.props.onPointerMove({ clientX: 72, currentTarget: { getBoundingClientRect: () => ({ left: 0, width: 600 }) } });
  assert.equal(nodes(component.render()).find((node) => node.props?.type === "range").props.value, 0);
  let toggles = nodes(component.render()).filter((node) => node.props?.type === "checkbox");
  assert.equal(toggles[2].props.disabled, true);
  toggles[0].props.onChange();
  tree = component.render();
  assert.equal(nodes(tree).filter((node) => node.type === "path").length, 1);
  toggles = nodes(tree).filter((node) => node.props?.type === "checkbox");
  toggles[1].props.onChange();
  assert.match(text(component.render()), /No equity curves to display/);
});

test("chart explains misaligned ranges and shows an observed point for one-day data", async () => {
  const component = await chart({ ...data, results: [{ ...data.results[0], equity: ["10000.00"] }, data.results[1]] });
  assert.match(text(component.render()), /equity dates are not aligned/);
  assert.equal(nodes(component.render()).filter((node) => node.type === "path").length, 1);
  const single = await chart({ ...data, dates: [dates[0]], results: [{ ...data.results[0], equity: ["10000.00"] }] });
  assert.equal(nodes(single.render()).filter((node) => node.type === "circle").length, 1);
});

test("comparison dashboard shows exact backend metrics, ties, missing values, and actual coverage", async () => {
  function MockChart() {}
  const ui = Object.fromEntries(["Badge", "Panel"].map((name) => [name, function Mock() {}]));
  const component = await mount("../src/components/comparison-results.tsx", {
    "../lib/comparison-chart": { comparisonStrategyLabel }, "./comparison-chart": { ComparisonChart: MockChart }, "./ui": ui,
  }, "ComparisonResults", { data });
  const tree = component.render();
  assert.equal(nodes(tree).find((node) => node.type === MockChart).props.data, data);
  const rows = nodes(tree).filter((node) => node.type === "tr");
  const returns = rows.find((row) => text(row).startsWith("Total return"));
  assert.equal(nodes(returns).filter((node) => node.props?.tone === "positive").length, 2);
  assert.match(text(returns), /2\.0000%Joint leader/);
  const sharpe = rows.find((row) => text(row).startsWith("Sharpe ratio"));
  assert.equal(nodes(sharpe).filter((node) => node.props?.tone === "positive").length, 0);
  assert.match(text(sharpe), /UnavailableUnavailableUnavailable/);
  const trades = rows.find((row) => text(row).startsWith("Trade count"));
  assert.match(text(trades), /02Unavailable/);
  assert.equal(nodes(trades).filter((node) => node.props?.tone === "positive").length, 0);
  for (const expected of ["12.3456%", "-1.2345%", "Requested 2024-01-01 to 2024-01-31", "Observed 2024-01-05 to 2024-01-09", "Too few bars for warm-up.", "Insufficient observations.", data.disclaimer]) assert.ok(text(tree).includes(expected), expected);
  assert.ok(nodes(tree).some((node) => node.props?.role === "region" && node.props.tabIndex === 0));
});

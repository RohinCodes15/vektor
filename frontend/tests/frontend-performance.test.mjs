import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { comparisonChartGeometry, comparisonStrategyLabel } from "../src/lib/comparison-chart.ts";
import { nearestBacktestPoint } from "../src/lib/backtest-chart.ts";
import { formatMoney } from "../src/lib/portfolio-values.ts";


test("25,000 comparison observations build geometry once across 21 cursor renders, refreshing on series/data changes", async () => {
  const dates = Array.from({ length: 5000 }, (_, i) => new Date(Date.UTC(2000, 0, i + 1)).toISOString().slice(0, 10));
  const data = { dates, results: Array.from({ length: 5 }, (_, j) => ({ status: "available", strategy: { kind: "buy_and_hold" }, equity: dates.map((_, i) => (10000 + i + j).toFixed(2)) })) };
  let builds = 0;
  const component = await mount("../src/components/comparison-chart.tsx", {
    "../lib/comparison-chart": { comparisonStrategyLabel, comparisonChartGeometry: (...args) => { builds++; return comparisonChartGeometry(...args); } },
    "../lib/backtest-chart": { nearestBacktestPoint }, "../lib/portfolio-values": { formatMoney },
  }, "ComparisonChart", { data });
  let tree = component.render();
  const paths = nodes(tree).filter((node) => node.type === "path").map((node) => node.props.d);
  for (let i = 0; i < 20; i++) {
    nodes(tree).find((node) => node.props?.type === "range").props.onChange({ target: { value: String(i) } });
    tree = component.render();
  }
  assert.equal(builds, 1);
  assert.deepEqual(nodes(tree).filter((node) => node.type === "path").map((node) => node.props.d), paths);
  assert.equal(nodes(tree).find((node) => node.props?.type === "range").props["aria-valuetext"], dates[19]);
  nodes(tree).find((node) => node.props?.type === "checkbox").props.onChange();
  tree = component.render();
  assert.equal(builds, 2);
  assert.equal(nodes(tree).filter((node) => node.type === "path").length, 4);
  component.render({ data: { ...data, results: data.results.map((result) => ({ ...result, equity: result.equity.map(() => "20000.00") })) } });
  assert.equal(builds, 3);
});

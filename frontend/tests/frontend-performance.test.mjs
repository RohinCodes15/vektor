import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { comparisonChartGeometry, comparisonStrategyLabel } from "../src/lib/comparison-chart.ts";
import { nearestBacktestPoint } from "../src/lib/backtest-chart.ts";
import { formatMoney, formatTotalPnl } from "../src/lib/portfolio-values.ts";

const ui = Object.fromEntries(["Badge", "Button", "Field", "Panel", "MetricCard"].map((name) => [name, function Mock() {}]));
function MockAllocation() {}
function MockPerformance() {}
function MockTransactions() {}

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

test("dashboard holds child section elements stable when holdings finish; trade refresh still updates them", async () => {
  let resolve;
  const component = await mount("../src/components/portfolio-dashboard.tsx", {
    "../lib/api": { getPortfolioHoldings: () => new Promise((done) => { resolve = done; }) },
    "../lib/portfolio-values": { formatMoney, formatTotalPnl }, "./ui": ui,
    "./portfolio-allocation": { PortfolioAllocationSection: MockAllocation },
    "./portfolio-performance": { PortfolioPerformance: MockPerformance }, "./transaction-history": { TransactionHistory: MockTransactions },
  }, "PortfolioDetails", { id: "portfolio" });
  const initial = nodes(component.render()).filter((node) => [MockAllocation, MockPerformance, MockTransactions].includes(node.type));
  component.flush(); await Promise.resolve();
  resolve({ equity: "100.00", cash: "100.00", realized_pnl: "0.00", unrealized_pnl: "0.00", holdings: [], valued_at: "2026-11-09T00:00:00Z" });
  await Promise.resolve(); await Promise.resolve();
  const loaded = nodes(component.render()).filter((node) => [MockAllocation, MockPerformance, MockTransactions].includes(node.type));
  loaded.forEach((node, index) => assert.equal(node, initial[index]));
  loaded[2].props.onTrades();
  const refreshed = nodes(component.render()).find((node) => node.type === MockPerformance);
  assert.notEqual(refreshed, loaded[1]);
  assert.equal(refreshed.props.refreshVersion, 1);
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";

const ui = Object.fromEntries(["Badge", "MetricCard", "Panel"].map((name) => [name, function Mock(props) { return { type: name, props }; }]));
function MockChart(props) { return { type: "BacktestChart", props }; }
function MockTrades(props) { return { type: "BacktestTrades", props }; }
function MockInsights(props) { return { type: "BacktestInsights", props }; }
const result = {
  id: "123e4567-e89b-12d3-a456-426614174000",
  bars: 2, first_date: "2024-01-02", last_date: "2024-01-03", config: { symbols: ["AAPL"] }, warnings: ["Sharpe ratio is unavailable."],
  metrics: { total_return_pct: "5.2500", annualized_return_pct: null, sharpe_ratio: null, volatility_pct: "12.3000", max_drawdown_pct: "-3.1000", win_rate_pct: null },
  equity_curve: [
    { date: "2024-01-02", cash: "10000.00", positions_value: "0.00", equity: "10000.00", drawdown_pct: "0" },
    { date: "2024-01-03", cash: "0.00", positions_value: "10525.00", equity: "10525.00", drawdown_pct: "-3.1000" },
  ],
  trades: [{ symbol: "AAPL", side: "buy", signal_date: "2024-01-02", fill_date: "2024-01-03", quantity: 10, price: "100.0000", notional: "1000.00", fee: "0.00", realized_pnl: null }],
};

async function render(state) {
  const component = await mount("../src/components/backtest-results.tsx", { "../lib/api": {}, "./backtest-chart": { BacktestChart: MockChart }, "./backtest-trades": { BacktestTrades: MockTrades }, "./backtest-insights": { BacktestInsights: MockInsights }, "./ui": ui }, "BacktestResults", { state });
  return component.render();
}

test("results expose loading, empty, and error states", async () => {
  assert.ok(nodes(await render({ status: "idle" })).some((node) => node.props?.children === "Configure a strategy to begin."));
  assert.ok(nodes(await render({ status: "loading" })).some((node) => node.props?.children === "Running paper simulation…"));
  assert.equal(nodes(await render({ status: "error", message: "Provider unavailable." })).find((node) => node.props?.role === "alert")?.props.children, "Provider unavailable.");
});

test("results show exact metrics, unavailable values, and both interactive curves", async () => {
  const tree = await render({ status: "success", data: result });
  const cards = nodes(tree).filter((node) => node.props?.label);
  assert.equal(cards.find((card) => card.props.label === "Total return").props.value, "5.2500%");
  assert.equal(cards.find((card) => card.props.label === "Annualized return").props.value, "Unavailable");
  assert.equal(cards.find((card) => card.props.label === "Sharpe ratio").props.value, "Unavailable");
  const charts = nodes(tree).filter((node) => node.type === MockChart);
  assert.deepEqual(charts.map((chart) => chart.props.kind), ["equity", "drawdown"]);
  assert.ok(charts.every((chart) => chart.props.points === result.equity_curve));
  assert.equal(nodes(tree).find((node) => node.type === MockTrades)?.props.trades, result.trades);
  const insights = nodes(tree).find((node) => node.type === MockInsights);
  assert.equal(insights.props.backtestId, result.id);
  assert.equal(insights.key, result.id);
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { mount, nodes } from "./component-runtime.mjs";
import { comparisonStrategyLabel } from "../src/lib/comparison-chart.ts";
import { formatMoney } from "../src/lib/portfolio-values.ts";

const metrics = { final_equity: "10321.09", total_return_pct: "3.2109", annualized_return_pct: "12.3456", volatility_pct: "9.8765", max_drawdown_pct: "-2.4567", sharpe_ratio: "1.2345", win_rate_pct: null, trades: 4, total_fees: "2.50" };
const strategy = { kind: "sma_crossover", fast_window: 10, slow_window: 30 };
const secondStrategy = { kind: "sma_crossover", fast_window: 20, slow_window: 50 };
function segment(dates, values, segmentMetrics) {
  return { first_date: dates[0], last_date: dates.at(-1), bars: dates.length, metrics: segmentMetrics, warnings: ["Win rate unavailable for this segment."], equity_curve: dates.map((date, i) => ({ date, cash: "0.00", positions_value: values[i], equity: values[i], drawdown_pct: i === 0 ? "0.0000" : "-2.4567" })) };
}
const train = segment(["2024-01-02", "2024-01-03", "2024-01-04"], ["10000.00", "10500.00", "10321.09"], metrics);
const testSegment = segment(["2024-01-05", "2024-01-08"], ["10000.00", "9800.00"], { ...metrics, final_equity: "9800.00", total_return_pct: "-2.0000", annualized_return_pct: null, sharpe_ratio: null, win_rate_pct: "0.0000", trades: 0 });
const data = {
  config: { symbol: "AAPL", start: "2024-01-01", end: "2024-01-31", starting_cash: "10000.00", objective: "total_return_pct" },
  bars: 5, split: { train_pct: 70, train_bars: 3, train_first_date: train.first_date, train_last_date: train.last_date, test_bars: 2, test_first_date: testSegment.first_date, test_last_date: testSegment.last_date },
  candidates_total: 4, candidates_evaluated: 3, candidates_skipped: 1, candidates_unranked: 1,
  ranked: [{ rank: 1, strategy, objective_value: "3.2109", train_metrics: metrics }, { rank: 2, strategy: secondStrategy, objective_value: "1.0000", train_metrics: { ...metrics, total_return_pct: "1.0000" } }],
  selected: { strategy, train, test: testSegment, overfitting: { annualized_return_gap_pct: null, sharpe_gap: null, max_drawdown_gap_pct: "-1.1234", flags: [{ code: "return_reversal", message: "Training gain became a test loss." }, { code: "few_trades", message: "Few trades limit confidence." }] } },
  selection_reason: null, limitations: ["Bounded grid search can overfit."], disclaimer: "Paper simulation only; past results do not predict returns.",
};
const ui = Object.fromEntries(["Badge", "MetricCard", "Panel"].map((name) => [name, function Mock() {}]));
function MockChart() {}
async function render(input = data) {
  const component = await mount("../src/components/optimization-results.tsx", {
    "../lib/comparison-chart": { comparisonStrategyLabel }, "../lib/portfolio-values": { formatMoney },
    "./backtest-chart": { BacktestChart: MockChart }, "./ui": ui,
  }, "OptimizationResults", { data: input });
  return component.render();
}
function text(element) {
  if (Array.isArray(element)) return element.map(text).join("");
  if (element === null || element === undefined || typeof element === "boolean") return "";
  return typeof element === "object" ? text(element.props?.children) : String(element);
}

test("optimization dashboard preserves backend ranks, parameters, objective values and search counts", async () => {
  const tree = await render();
  const cards = nodes(tree).filter((node) => node.type === ui.MetricCard);
  assert.deepEqual(cards.map((node) => [node.props.label, node.props.value]), [["Grid candidates", "4"], ["Evaluated", "3"], ["Skipped", "1"], ["Unranked", "1"]]);
  const ranked = nodes(tree).find((node) => node.props?.className === "optimization-ranked");
  const rows = nodes(ranked).filter((node) => node.type === "tbody")[0].props.children;
  assert.equal(rows.length, 2);
  assert.match(text(rows[0]), /1SelectedSMA 10\/303\.2109%/);
  assert.match(text(rows[1]), /2SMA 20\/501\.0000%/);
  assert.equal(nodes(ranked).filter((node) => node.props?.children === "Selected").length, 1);
  assert.match(text(ranked), /In-sample only/);
  assert.equal(text(nodes(rows[0]).filter((node) => node.type === "td")[8]), "Unavailable");
});

test("optimization performance keeps training and holdout values separate, exact, and visibly labeled", async () => {
  const tree = await render();
  const performance = nodes(tree).find((node) => node.props?.className === "optimization-performance");
  assert.match(text(performance), /Training · In-sample/);
  assert.match(text(performance), /Test · Out-of-sample/);
  assert.match(text(performance), /2024-01-02 to 2024-01-04/);
  assert.match(text(performance), /2024-01-05 to 2024-01-08/);
  assert.match(text(performance), /3 trading days/);
  assert.match(text(performance), /2 trading days/);
  assert.match(text(performance), /Each segment starts independently with \$10,000\.00/);
  const rows = nodes(performance).filter((node) => node.type === "tr");
  assert.equal(text(rows.find((row) => text(row).startsWith("Total return"))), "Total return3.2109%-2.0000%");
  assert.equal(text(rows.find((row) => text(row).startsWith("Sharpe ratio"))), "Sharpe ratio1.2345Unavailable");
  assert.equal(text(rows.find((row) => text(row).startsWith("Trade count"))), "Trade count40");
  assert.equal(text(rows.find((row) => text(row).startsWith("Final equity"))), "Final equity$10,321.09$9,800.00");
  assert.ok(nodes(performance).some((node) => node.props?.role === "region" && node.props.tabIndex === 0));
});


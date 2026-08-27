import type { BacktestMetrics, BacktestOptimization, OptimizationObjective } from "../lib/api";
import { comparisonStrategyLabel } from "../lib/comparison-chart";
import { formatMoney } from "../lib/portfolio-values";
import { Badge, MetricCard, Panel } from "./ui";

const objectives: Readonly<Record<OptimizationObjective, string>> = {
  total_return_pct: "Total return", sharpe_ratio: "Sharpe ratio", max_drawdown_pct: "Max drawdown",
};
const metrics = [
  ["final_equity", "Final equity", "USD"], ["total_return_pct", "Total return", "%"],
  ["annualized_return_pct", "Annualized return", "%"], ["sharpe_ratio", "Sharpe ratio", ""],
  ["volatility_pct", "Volatility", "%"], ["max_drawdown_pct", "Max drawdown", "%"],
  ["win_rate_pct", "Win rate", "%"], ["trades", "Trade count", ""], ["total_fees", "Total fees", "USD"],
] as const satisfies readonly (readonly [keyof BacktestMetrics, string, string])[];

function metricValue(value: string | number | null, unit: string): string {
  return value === null ? "Unavailable" : unit === "USD" ? formatMoney(String(value)) : `${value}${unit}`;
}

export function OptimizationResults({ data }: { data: BacktestOptimization }) {
  const selected = data.selected;
  const objectiveUnit = data.config.objective === "sharpe_ratio" ? "" : "%";
  return <section className="optimization-results" aria-labelledby="optimization-results-title">
    <div className="section-heading"><div><span className="eyebrow">OPTIMIZE / RESULTS</span><h2 id="optimization-results-title">Optimization results</h2></div><Badge>{data.config.symbol} · Paper only</Badge></div>
    <p className="chart-provenance">Requested {data.config.start} to {data.config.end} · {data.bars} observed trading days · Ranked by training {objectives[data.config.objective].toLowerCase()} (higher is better).</p>
    <div className="optimization-counts">
      <MetricCard label="Grid candidates" value={String(data.candidates_total)} detail="Valid parameter combinations" />
      <MetricCard label="Evaluated" value={String(data.candidates_evaluated)} detail="Training candidates evaluated" />
      <MetricCard label="Skipped" value={String(data.candidates_skipped)} detail="Insufficient warm-up observations" />
      <MetricCard label="Unranked" value={String(data.candidates_unranked)} detail="Training objective undefined" />
    </div>
    <Panel className="optimization-ranked" aria-label="Ranked training parameters">
      <div className="panel-heading"><h3>Ranked parameters · In-sample only</h3><Badge>{data.ranked.length} returned</Badge></div>
      <p className="muted text-xs">Rank order comes from training data. Only the selected parameters are evaluated out of sample.</p>
      {data.ranked.length === 0 ? <p role="status">No ranked candidates returned. {data.selection_reason}</p> : <div className="trade-table-scroll" tabIndex={0} role="region" aria-label="Ranked optimization parameters, scroll horizontally">
        <table className="backtest-trade-table optimization-table"><caption>Training (in-sample) · {data.split.train_first_date} to {data.split.train_last_date} · {data.split.train_bars} trading days</caption>
          <thead><tr><th scope="col">Rank</th><th scope="col">Parameters</th><th scope="col">Objective · {objectives[data.config.objective]}</th>{metrics.map(([key, label]) => <th scope="col" key={key}>{label}</th>)}</tr></thead>
          <tbody>{data.ranked.map((candidate) => <tr key={candidate.rank} className={candidate.rank === 1 && selected ? "optimization-selected" : undefined}>
            <th scope="row">{candidate.rank}{candidate.rank === 1 && selected && <Badge>Selected</Badge>}</th>
            <td>{comparisonStrategyLabel(candidate.strategy)}</td><td className="mono">{metricValue(candidate.objective_value, objectiveUnit)}</td>
            {metrics.map(([key, , unit]) => <td className="mono" key={key}>{metricValue(candidate.train_metrics[key], unit)}</td>)}
          </tr>)}</tbody>
        </table>
      </div>}
    </Panel>
    {selected ? <>
      <Panel className="optimization-performance">
        <div className="panel-heading"><div><h3>Selected parameters · {comparisonStrategyLabel(selected.strategy)}</h3><p className="muted text-xs">Selected on training performance; test results never determine the ranking.</p></div><Badge>Chronological holdout</Badge></div>
        <p className="optimization-segment-note">Each segment starts independently with {formatMoney(data.config.starting_cash)} virtual cash and no position. Curves are separate simulations, not a continuous account history. Segment lengths differ.</p>
        <div className="trade-table-scroll" tabIndex={0} role="region" aria-label="In-sample versus out-of-sample performance, scroll horizontally">
          <table className="backtest-trade-table optimization-table"><caption>Selected strategy performance · Missing metrics remain unavailable</caption>
            <thead><tr><th scope="col">Metric</th><th scope="col">Training · In-sample<br />{selected.train.first_date} to {selected.train.last_date}<br />{selected.train.bars} trading days</th><th scope="col">Test · Out-of-sample<br />{selected.test.first_date} to {selected.test.last_date}<br />{selected.test.bars} trading days</th></tr></thead>
            <tbody>{metrics.map(([key, label, unit]) => <tr key={key}><th scope="row">{label}</th><td className="mono">{metricValue(selected.train.metrics[key], unit)}</td><td className="mono">{metricValue(selected.test.metrics[key], unit)}</td></tr>)}</tbody>
          </table>
        </div>
      </Panel>
    </> : <Panel className="chart-state" role="status"><h3>No strategy selected</h3><p>{data.selection_reason}</p></Panel>}
    {data.limitations.length > 0 && <Panel className="optimization-notes"><h3>Limitations</h3><ul>{data.limitations.map((note, i) => <li key={i}>{note}</li>)}</ul></Panel>}
    <p className="chart-provenance">Yahoo Finance completed daily history · {data.disclaimer}</p>
  </section>;
}

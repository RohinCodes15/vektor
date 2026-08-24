import type { BacktestComparison, BacktestMetrics } from "../lib/api";
import { comparisonStrategyLabel } from "../lib/comparison-chart";
import { ComparisonChart } from "./comparison-chart";
import { Badge, Panel } from "./ui";

const metrics = [
  ["total_return_pct", "Total return", "%"], ["annualized_return_pct", "Annualized return", "%"],
  ["sharpe_ratio", "Sharpe ratio", ""], ["volatility_pct", "Volatility", "%"],
  ["max_drawdown_pct", "Max drawdown", "%"], ["win_rate_pct", "Win rate", "%"], ["trades", "Trade count", ""],
] as const satisfies readonly (readonly [keyof BacktestMetrics, string, string])[];

export function ComparisonResults({ data }: { data: BacktestComparison }) {
  return <section className="comparison-results" aria-labelledby="comparison-results-title">
    <div className="section-heading"><div><span className="eyebrow">COMPARE / RESULTS</span><h2 id="comparison-results-title">Comparison results</h2></div><Badge>{data.config.symbol} · {data.bars} trading days</Badge></div>
    <p className="chart-provenance">Requested {data.config.start} to {data.config.end} · Observed {data.first_date} to {data.last_date}. Available strategies share these returned trading dates; calendar gaps stay unfilled.</p>
    <Panel><div className="panel-heading"><h3>Equity curves</h3><Badge>Virtual USD</Badge></div><ComparisonChart data={data} /></Panel>
    <Panel className="comparison-metrics">
      <div className="panel-heading"><h3>Performance side by side</h3><Badge>Backend metric leaders</Badge></div>
      <p className="muted text-xs">Leader badges describe the returned comparison, including ties. Lower volatility is preferred; other ranked metrics prefer higher values. Trade count is unranked.</p>
      <div className="trade-table-scroll" tabIndex={0} role="region" aria-label="Strategy comparison metrics, scroll horizontally">
        <table className="backtest-trade-table comparison-table"><caption>Paper performance · Strategy 1 is the baseline · Unavailable metrics are never treated as zero.</caption>
          <thead><tr><th scope="col">Metric</th>{data.results.map((result, i) => <th key={i} scope="col">{i + 1}. {comparisonStrategyLabel(result.strategy)}{i === 0 && <span className="muted"> · Baseline</span>}</th>)}</tr></thead>
          <tbody>{metrics.map(([key, label, suffix]) => {
            const leader = data.leaders.find((item) => item.metric === key);
            return <tr key={key}><th scope="row">{label}</th>{data.results.map((result, i) => {
              const value = result.metrics?.[key];
              const leading = value !== null && value !== undefined && leader?.leaders.includes(i);
              return <td key={i} className={leading ? "comparison-leader" : undefined}>{value === null || value === undefined ? <span className="muted">Unavailable</span> : <span className="mono">{value}{suffix}</span>}{leading && <Badge tone="positive">{leader && leader.leaders.length > 1 ? "Joint leader" : "Leader"}</Badge>}</td>;
            })}</tr>;
          })}</tbody>
        </table>
      </div>
      <details className="comparison-notes"><summary>Availability and metric notes</summary>
        {data.results.map((result, i) => <div key={i}><h4>{i + 1}. {comparisonStrategyLabel(result.strategy)}</h4>{result.status === "unavailable" && <p>{result.unavailable_reason}</p>}{result.warnings.map((warning, j) => <p key={j}>{warning}</p>)}</div>)}
        {data.leaders.filter((leader) => leader.reason !== null).map((leader) => <p key={leader.metric}>{metrics.find(([key]) => key === leader.metric)?.[1]}: {leader.reason}</p>)}
      </details>
    </Panel>
    <p className="chart-provenance">Yahoo Finance completed daily history · {data.disclaimer}</p>
  </section>;
}

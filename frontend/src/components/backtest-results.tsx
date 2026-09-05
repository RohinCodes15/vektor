import type { Backtest } from "../lib/api";
import { BacktestChart } from "./backtest-chart";
import { BacktestTrades } from "./backtest-trades";
import { BacktestInsights } from "./backtest-insights";
import { Badge, MetricCard, Panel } from "./ui";

export type BacktestResultState = { status: "idle" | "loading" } | { status: "error"; message: string } | { status: "success"; data: Backtest };

const metrics = [
  { key: "total_return_pct", label: "Total return", detail: "Change from starting virtual capital", suffix: "%" },
  { key: "annualized_return_pct", label: "Annualized return", detail: "252-day annualization · Requires one return", suffix: "%" },
  { key: "sharpe_ratio", label: "Sharpe ratio", detail: "Zero risk-free rate · Requires non-zero volatility", suffix: "" },
  { key: "volatility_pct", label: "Volatility", detail: "Annualized · Requires two daily returns", suffix: "%" },
  { key: "max_drawdown_pct", label: "Max drawdown", detail: "Largest peak-to-trough decline", suffix: "%" },
  { key: "win_rate_pct", label: "Win rate", detail: "Requires at least one closed trade", suffix: "%" },
] as const;

export function BacktestResults({ state }: { state: BacktestResultState }) {
  const result = state.status === "success" ? state.data : null;
  return (
    <section className="backtest-results" aria-labelledby="backtest-results-title" aria-busy={state.status === "loading"}>
      <div className="section-heading"><div><span className="eyebrow">SIMULATION / RESULTS</span><h2 id="backtest-results-title">Backtest results</h2></div>{result && <Badge>{result.config.symbols.join(" · ")} · {result.bars} days</Badge>}</div>
      {state.status === "idle" && <Panel className="chart-state"><span className="empty-icon" aria-hidden="true">⌁</span><h3>Configure a strategy to begin.</h3><p>Returned simulation metrics and daily curves will appear here.</p></Panel>}
      {state.status === "loading" && <Panel className="chart-state" role="status"><h3>Running paper simulation…</h3><p>Loading historical bars and calculating the strategy.</p></Panel>}
      {state.status === "error" && <Panel className="chart-state"><h3>Backtest unavailable</h3><p role="alert">{state.message}</p></Panel>}
      {result && <>
        <p className="sr-only" role="status">Backtest complete. {result.bars} trading days and {result.trades.length} fills returned.</p>
        <div className="metrics-grid backtest-metrics">{metrics.map((metric) => {
          const value = result.metrics[metric.key];
          return <MetricCard key={metric.key} label={metric.label} value={value === null ? "Unavailable" : `${value}${metric.suffix}`} detail={metric.detail} />;
        })}</div>
        {result.warnings.length > 0 && <Panel className="backtest-warnings"><h3>Metric notes</h3><ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></Panel>}
        <div className="backtest-chart-grid">
          <Panel><div className="panel-heading"><div><h3>Equity curve</h3><p className="muted text-xs">Virtual account value at each completed close</p></div><Badge>USD</Badge></div><BacktestChart points={result.equity_curve} kind="equity" /></Panel>
          <Panel><div className="panel-heading"><div><h3>Drawdown</h3><p className="muted text-xs">Decline from the highest equity reached</p></div><Badge>Peak-relative</Badge></div><BacktestChart points={result.equity_curve} kind="drawdown" /></Panel>
        </div>
        <BacktestTrades trades={result.trades} />
        <BacktestInsights key={result.id} backtestId={result.id} />
        <p className="chart-provenance backtest-provenance">Yahoo Finance completed daily history · {result.first_date} to {result.last_date} · Paper simulation only</p>
      </>}
    </section>
  );
}

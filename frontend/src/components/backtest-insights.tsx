"use client";

import { useBacktestAnalysis } from "../hooks/use-backtest-analysis";
import { Badge, Button, Panel } from "./ui";

const sections = [
  ["strategy_behavior", "Strategy behavior"], ["strengths", "Strengths"], ["weaknesses", "Weaknesses"],
  ["risk_factors", "Risks"], ["limitations", "Limitations"],
] as const;

export function BacktestInsights({ backtestId }: { backtestId: string }) {
  const { state, load } = useBacktestAnalysis();
  const data = state.status === "success" || state.status === "unavailable" ? state.data : null;
  const interpretation = data?.interpretation;
  const facts = new Map(data?.facts.map((fact) => [fact.id, fact]));
  const loading = state.status === "loading";

  return (
    <Panel className="backtest-insights" aria-labelledby="backtest-insights-title" aria-busy={loading}>
      <div className="panel-heading">
        <div><h3 id="backtest-insights-title">AI Insights</h3><p className="muted text-xs">Educational interpretation of this paper simulation. AI explanations can be wrong.</p></div>
        <Badge>Paper only</Badge>
      </div>
      {state.status === "idle" && <p className="muted">Request an explanation from the configured AI provider. No insights have been generated.</p>}
      {loading && <p role="status">Analyzing this backtest… This may take a few minutes.</p>}
      {state.status === "error" && <p role="alert">{state.message}</p>}
      {state.status === "unavailable" && <p role="status">AI insights unavailable: {state.data.unavailable_reason}</p>}
      {interpretation && <>
        <div className="insights-summary"><h4>Strategy summary</h4><p>{interpretation.summary}</p></div>
        <div className="insights-grid">{sections.map(([key, label]) => <section key={key} aria-label={label}>
          <h4>{label}</h4>
          {interpretation[key].length === 0 ? <p className="muted">None returned by the provider.</p> : <ul>{interpretation[key].map((insight, index) => <li key={index}>
            <p>{insight.text}</p>
            <p className="muted text-xs">Measured evidence: {insight.evidence.map((id) => {
              const fact = facts.get(id)!;
              return `${fact.label}: ${fact.value}`;
            }).join(" · ")}</p>
          </li>)}</ul>}
        </section>)}</div>
      </>}
      {data && <>
        <details><summary>Measured facts · computed locally</summary><dl className="insights-facts">{data.facts.map((fact) => <div key={fact.id}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl></details>
        <p className="muted text-xs">{data.disclaimer}</p>
      </>}
      <Button type="button" variant="secondary" disabled={loading} onClick={() => void load(backtestId)}>
        {loading ? "Analyzing…" : state.status === "idle" ? "Generate AI insights" : state.status === "error" || state.status === "unavailable" ? "Try again" : "Regenerate AI insights"}
      </Button>
    </Panel>
  );
}

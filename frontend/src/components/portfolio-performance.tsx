"use client";

import { useEffect, useMemo, useState } from "react";
import { getPortfolioAnalytics, getPortfolioEquityHistory, type PortfolioAnalytics, type EquitySnapshot } from "../lib/api";
import { historyRange, type HistoryRange } from "../lib/history-range";
import { EquityChart } from "./equity-chart";
import { Badge, Button, MetricCard, Panel } from "./ui";

type Result = { key: string } & ({ status: "success"; metrics: PortfolioAnalytics; history: readonly EquitySnapshot[] } | { status: "error"; message: string });

const metrics = [
  { key: "total_return_pct", label: "Total return", detail: "Deposit-adjusted · Requires a funded snapshot" },
  { key: "latest_daily_return_pct", label: "Daily return", detail: "Latest daily observation · Requires a valid prior equity" },
  { key: "volatility_pct", label: "Volatility", detail: "Annualized · Requires two daily returns" },
  { key: "max_drawdown_pct", label: "Max drawdown", detail: "Deposit-adjusted · Requires one daily return" },
  { key: "sharpe_ratio", label: "Sharpe ratio", detail: "Annualized · Requires two daily returns and non-zero volatility" },
] as const;

export function PortfolioPerformance({ id, refreshVersion = 0 }: { id: string; refreshVersion?: number }) {
  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [range, setRange] = useState<HistoryRange>("ALL");
  const key = `${id}:${refreshVersion}:${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted) return;
      try {
        const [metrics, history] = await Promise.all([getPortfolioAnalytics(id, controller.signal), getPortfolioEquityHistory(id, controller.signal)]);
        if (!controller.signal.aborted) setResult({ key, status: "success", metrics, history });
      } catch (error) {
        if (!controller.signal.aborted) {
          setResult({ key, status: "error", message: error instanceof Error ? error.message : "Portfolio analytics unavailable." });
          controller.abort();
        }
      }
    });
    return () => controller.abort();
  }, [id, key]);
  const current = result?.key === key ? result : null;
  const data = current?.status === "success" ? current : null;
  const observations = useMemo(() => {
    if (!data) return [];
    if (range === "ALL") return data.history;
    const dates = historyRange(range);
    return data.history.filter((item) => {
      const day = new Date(item.taken_at).toISOString().slice(0, 10);
      return day >= dates.start && day <= dates.end;
    });
  }, [data, range]);
  return (
    <section className="portfolio-performance" aria-labelledby="performance-title" aria-busy={!current}>
      <div className="section-heading"><div><span className="eyebrow">PERFORMANCE / RECORDED HISTORY</span><h2 id="performance-title">Portfolio performance</h2></div><Badge>Paper snapshots · USD</Badge></div>
      <div className="metrics-grid analytics-metrics">{metrics.map((metric) => {
        const value = data?.metrics[metric.key];
        return <MetricCard key={metric.key} label={metric.label} value={!data ? "—" : value === null ? "Unavailable" : `${value}${metric.key === "sharpe_ratio" ? "" : "%"}`} detail={metric.detail} />;
      })}</div>
      <Panel className="performance-panel analytics-chart">
        {!current && <p className="chart-state" role="status">Loading recorded equity and analytics…</p>}
        {current?.status === "error" && <div className="chart-state"><h3>Performance unavailable</h3><p role="alert">{current.message}</p><Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Retry performance</Button></div>}
        {data && <>
          <div className="panel-heading"><div><h3>Historical equity</h3><p className="muted text-xs">Chart range only · Metrics above use all recorded history</p></div><Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Refresh performance</Button></div>
          <p className="chart-provenance">{data.metrics.snapshots} snapshots · {data.metrics.daily_observations} UTC daily observations{data.metrics.as_of && <> · Metrics as of <time dateTime={data.metrics.as_of}>{data.metrics.as_of}</time></>}</p>
          <p className="chart-provenance">Unavailable metrics lack sufficient valid history or have an undefined denominator. Volatility and Sharpe use √252 annualization; Sharpe assumes a zero risk-free rate. Returns can span days without snapshots.</p>
          <div className="history-ranges" role="group" aria-label="Equity history date range">{(["1M", "3M", "6M", "1Y", "ALL"] as const).map((value) => <Button type="button" key={value} variant={range === value ? "primary" : "secondary"} aria-pressed={range === value} onClick={() => setRange(value)}>{value}</Button>)}</div>
          {data.history.length === 0 ? <div className="chart-state" role="status"><h3>No equity snapshots recorded.</h3><p>History appears only after actual snapshots are recorded through the local portfolio API. Past values are never reconstructed.</p></div> : observations.length === 0 ? <div className="chart-state" role="status"><h3>No snapshots in this range.</h3><p>Choose a wider range to explore recorded equity.</p></div> : <EquityChart key={`${key}:${range}`} snapshots={observations} />}
        </>}
      </Panel>
    </section>
  );
}

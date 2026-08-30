"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { BacktestEquityPoint } from "../lib/api";
import { backtestChartGeometry, nearestBacktestPoint } from "../lib/backtest-chart";
import { formatMoney } from "../lib/portfolio-values";

type ChartKind = "equity" | "drawdown";
const axisNumber = new Intl.NumberFormat("en-US", { maximumSignificantDigits: 5 });

export function BacktestChart({ points, kind }: { points: readonly BacktestEquityPoint[]; kind: ChartKind }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [index, setIndex] = useState<number | null>(null);
  const slider = useId();
  const values = useMemo(() => points.map((point) => ({ date: point.date, value: Number(kind === "equity" ? point.equity : point.drawdown_pct) })), [kind, points]);
  const geometry = useMemo(() => backtestChartGeometry(values, width), [values, width]);
  const selectedIndex = Math.min(index ?? points.length - 1, points.length - 1);
  const selected = points[selectedIndex];
  const active = index === null ? undefined : geometry.points[selectedIndex];
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(160, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  if (!selected) return <div className="chart-state" role="status"><h3>No observations returned.</h3><p>The simulation completed without an equity curve to display.</p></div>;
  const exactValue = kind === "equity" ? formatMoney(selected.equity) : `${selected.drawdown_pct}%`;
  const label = kind === "equity" ? "Equity" : "Drawdown";
  const tooltipX = active ? Math.max(4, Math.min(active.x - 70, width - 144)) : 0;
  function selectAt(clientX: number, left: number, boundsWidth: number): void {
    setIndex(nearestBacktestPoint(geometry.points, (clientX - left) / boundsWidth * width));
  }
  return (
    <div className={`backtest-chart backtest-${kind}-chart`} ref={container}>
      <div className="chart-price"><div><span className="eyebrow">{label.toUpperCase()} / {kind === "equity" ? "VIRTUAL USD" : "PERCENT"}</span><p>{exactValue}</p></div><span className="mono muted text-xs">{selected.date}<br />Completed daily close</span></div>
      <svg className="price-plot" width="100%" height="280" viewBox={`0 0 ${width} 280`} role="img" aria-label={`Backtest ${label.toLowerCase()}, ${points[0].date} to ${points.at(-1)!.date}`} onPointerMove={(event) => { const bounds = event.currentTarget.getBoundingClientRect(); selectAt(event.clientX, bounds.left, bounds.width); }} onPointerDown={(event) => { const bounds = event.currentTarget.getBoundingClientRect(); selectAt(event.clientX, bounds.left, bounds.width); }} onPointerLeave={() => setIndex(null)} onPointerCancel={() => setIndex(null)}>
        <desc>Returned simulation observations only. Use the slider for keyboard access.</desc>
        {geometry.valueTicks.map((tick, position) => <g key={position}><line className="chart-grid-line" x1={geometry.plot.left} x2={geometry.plot.right} y1={tick.y} y2={tick.y} /><text className="chart-axis-label" x={geometry.plot.left - 10} y={tick.y + 4} textAnchor="end">{axisNumber.format(tick.value)}{kind === "drawdown" ? "%" : ""}</text></g>)}
        {geometry.zeroY !== null && <line className="chart-zero-line" x1={geometry.plot.left} x2={geometry.plot.right} y1={geometry.zeroY} y2={geometry.zeroY} />}
        {geometry.dateTicks.map((tick, position) => <text key={tick.date} className="chart-axis-label" x={tick.x} y={266} textAnchor={geometry.dateTicks.length === 1 ? "middle" : position === 0 ? "start" : position === geometry.dateTicks.length - 1 ? "end" : "middle"}>{tick.date}</text>)}
        <path className="backtest-chart-line" d={geometry.path} />
        {geometry.points.length === 1 && <circle className="chart-point" cx={geometry.points[0].x} cy={geometry.points[0].y} r="4" />}
        {active && <g className="chart-crosshair" aria-hidden="true"><line x1={active.x} x2={active.x} y1={geometry.plot.top} y2={geometry.plot.bottom} /><circle className="chart-point" cx={active.x} cy={active.y} r="4" /><g transform={`translate(${tooltipX},28)`}><rect className="chart-tooltip-bg" width="140" height="52" rx="5" /><text x="10" y="20">{selected.date}</text><text className="chart-tooltip-price" x="10" y="40">{exactValue}</text></g></g>}
      </svg>
      <div className="chart-explorer"><label htmlFor={slider}>Explore {label.toLowerCase()}</label><input id={slider} type="range" min="0" max={points.length - 1} step="1" value={selectedIndex} aria-valuetext={`${selected.date}, ${label.toLowerCase()} ${exactValue}`} onChange={(event) => setIndex(Number(event.target.value))} onFocus={() => setIndex(selectedIndex)} onBlur={() => setIndex(null)} /><span>Arrow keys or drag · {points.length} trading days</span></div>
    </div>
  );
}

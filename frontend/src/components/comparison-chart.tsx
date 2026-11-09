"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { BacktestComparison } from "../lib/api";
import { comparisonChartGeometry, comparisonStrategyLabel } from "../lib/comparison-chart";
import { nearestBacktestPoint } from "../lib/backtest-chart";
import { formatMoney } from "../lib/portfolio-values";

const colors = ["#86d5c1", "#a6a3ef", "#dfc58e", "#ed9faf", "#89c7ed"];
const dashes = [undefined, "8 3", "3 3", "10 3 2 3", "2 5"];
const axisNumber = new Intl.NumberFormat("en-US", { maximumSignificantDigits: 5 });

export function ComparisonChart({ data }: { data: BacktestComparison }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [index, setIndex] = useState<number | null>(null);
  const [hidden, setHidden] = useState<readonly number[]>([]);
  const slider = useId();
  const series = useMemo(() => data.results.map((result, i) => result.status === "available" && !hidden.includes(i) ? result.equity : null), [data.results, hidden]);
  const geometry = useMemo(() => comparisonChartGeometry(data.dates, series, width), [data.dates, series, width]);
  const paths = useMemo(() => geometry.curves.map((points) => points.map((point, j) => `${j ? "L" : "M"}${point.x},${point.y}`).join(" ")), [geometry]);
  const selected = Math.max(0, Math.min(index ?? data.dates.length - 1, data.dates.length - 1));
  const reference = geometry.curves.find((points) => points.length > 0) ?? [];
  const active = reference[selected];
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(160, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  function selectAt(clientX: number, left: number, boundsWidth: number): void {
    if (boundsWidth > 0 && reference.length) setIndex(nearestBacktestPoint(reference, (clientX - left) / boundsWidth * width));
  }

  return <div className="backtest-chart comparison-chart" ref={container}>
    <div className="comparison-legend">{data.results.map((result, i) => <label key={i} style={{ color: colors[i] }}>
      <input type="checkbox" checked={result.status === "available" && !hidden.includes(i)} disabled={result.status === "unavailable"} onChange={() => setHidden((current) => current.includes(i) ? current.filter((value) => value !== i) : [...current, i])} />
      {i + 1}. {comparisonStrategyLabel(result.strategy)}
    </label>)}</div>
    {reference.length === 0 ? <p role="status">No equity curves to display. Select an available strategy.</p> : <>
      <p className="mono text-xs">{data.dates[selected]} · Virtual USD at completed close</p>
      <ul className="comparison-values" aria-live="polite">{data.results.map((result, i) => !hidden.includes(i) && <li key={i} style={{ color: colors[i] }}>{i + 1}. {comparisonStrategyLabel(result.strategy)}: {geometry.aligned[i] && result.equity ? formatMoney(result.equity[selected]) : "Unavailable"}</li>)}</ul>
      <svg className="price-plot" width="100%" height="280" viewBox={`0 0 ${width} 280`} role="img" aria-label={`Strategy comparison equity, ${data.dates[0]} to ${data.dates.at(-1)}`} onPointerMove={(event) => { const bounds = event.currentTarget.getBoundingClientRect(); selectAt(event.clientX, bounds.left, bounds.width); }} onPointerDown={(event) => { const bounds = event.currentTarget.getBoundingClientRect(); selectAt(event.clientX, bounds.left, bounds.width); }} onPointerLeave={() => setIndex(null)} onPointerCancel={() => setIndex(null)}>
        <desc>Each line uses the same date and USD scale. Only aligned backend observations are plotted. Use the date slider for keyboard access.</desc>
        {geometry.valueTicks.map((tick, i) => <g key={i}><line className="chart-grid-line" x1={geometry.plot.left} x2={geometry.plot.right} y1={tick.y} y2={tick.y} /><text className="chart-axis-label" x={geometry.plot.left - 10} y={tick.y + 4} textAnchor="end">{axisNumber.format(tick.value)}</text></g>)}
        {geometry.dateTicks.map((tick, i) => <text key={tick.date} className="chart-axis-label" x={tick.x} y="266" textAnchor={i === 0 ? "start" : "end"}>{tick.date}</text>)}
        {geometry.curves.map((points, i) => points.length > 0 && <g key={i}>
          <path fill="none" stroke={colors[i]} strokeWidth="2" strokeDasharray={dashes[i]} d={paths[i]} />
          {(points.length === 1 || index !== null) && points[selected] && <circle fill={colors[i]} cx={points[selected].x} cy={points[selected].y} r="4" />}
        </g>)}
        {index !== null && active && <line className="chart-grid-line" x1={active.x} x2={active.x} y1={geometry.plot.top} y2={geometry.plot.bottom} />}
      </svg>
      <div className="chart-explorer"><label htmlFor={slider}>Explore comparison date</label><input id={slider} type="range" min="0" max={data.dates.length - 1} step="1" value={selected} aria-valuetext={data.dates[selected]} onChange={(event) => setIndex(Number(event.target.value))} onFocus={() => setIndex(selected)} onBlur={() => setIndex(null)} /><span>Arrow keys or drag · {data.dates.length} trading days</span></div>
    </>}
    {data.results.map((result, i) => result.status === "available" && result.equity.length !== data.dates.length && <p key={i} role="status">Strategy {i + 1}: equity dates are not aligned. Curve omitted; no missing values were filled.</p>)}
  </div>;
}

"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { EquitySnapshot } from "../lib/api";
import { formatMoney } from "../lib/portfolio-values";
import { formatChartPrice, nearestChartPoint, priceChartGeometry } from "../lib/price-chart";

export function EquityChart({ snapshots }: { snapshots: readonly EquitySnapshot[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [index, setIndex] = useState<number | null>(null);
  const slider = useId();
  // Numbers position the SVG only; labels and tooltips retain the exact recorded money strings.
  const geometry = useMemo(() => priceChartGeometry(snapshots.map((item) => ({ date: new Date(item.taken_at).toISOString(), close: Number(item.equity) })), width), [snapshots, width]);
  const selectedIndex = Math.min(index ?? snapshots.length - 1, snapshots.length - 1);
  const selected = snapshots[selectedIndex];
  const active = index === null ? undefined : geometry.points[selectedIndex];
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(160, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  if (!selected) return <p role="status">No recorded equity observations in this range.</p>;
  const tooltipX = active ? Math.max(4, Math.min(active.x - 70, width - 144)) : 0;
  return (
    <div className="price-chart equity-chart" ref={container}>
      <div className="chart-price"><div><span className="eyebrow">RECORDED EQUITY / VIRTUAL USD</span><p>{formatMoney(selected.equity)}</p></div><span className="mono muted text-xs"><time dateTime={selected.taken_at}>{selected.taken_at}</time><br />Prices as of {selected.prices_as_of ?? "cash only"}</span></div>
      <svg className="price-plot" width="100%" height="280" viewBox={`0 0 ${width} 280`} role="img" aria-label={`Recorded paper equity, ${snapshots[0].taken_at} to ${snapshots.at(-1)!.taken_at}`} onPointerMove={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        setIndex(nearestChartPoint(geometry.points, (event.clientX - bounds.left) / bounds.width * width));
      }} onPointerDown={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        setIndex(nearestChartPoint(geometry.points, (event.clientX - bounds.left) / bounds.width * width));
      }} onPointerLeave={() => setIndex(null)} onPointerCancel={() => setIndex(null)}>
        <desc>Recorded snapshots only. Lines connect observations; values between snapshots are unknown. Use the snapshot slider for keyboard access.</desc>
        {geometry.priceTicks.map((tick, position) => <g key={position}><line className="chart-grid-line" x1={geometry.plot.left} x2={geometry.plot.right} y1={tick.y} y2={tick.y} /><text className="chart-axis-label" x={geometry.plot.left - 10} y={tick.y + 4} textAnchor="end">{formatChartPrice(tick.value)}</text></g>)}
        {geometry.dateTicks.map((tick, position) => <text key={position} className="chart-axis-label" x={tick.x} y={266} textAnchor={geometry.dateTicks.length === 1 ? "middle" : position === 0 ? "start" : position === geometry.dateTicks.length - 1 ? "end" : "middle"}>{geometry.points[0].date.slice(0, 10) === geometry.points.at(-1)!.date.slice(0, 10) ? tick.date.slice(11, 19) : tick.date.slice(0, 10)}</text>)}
        <path className="chart-price-line" d={geometry.path} />
        {geometry.points.length === 1 && <circle className="chart-point" cx={geometry.points[0].x} cy={geometry.points[0].y} r="4" />}
        {active && <g className="chart-crosshair" aria-hidden="true"><line x1={active.x} x2={active.x} y1={geometry.plot.top} y2={geometry.plot.bottom} /><circle className="chart-point" cx={active.x} cy={active.y} r="4" /><g transform={`translate(${tooltipX},28)`}><rect className="chart-tooltip-bg" width="140" height="52" rx="5" /><text x="10" y="20">{new Date(selected.taken_at).toISOString().slice(0, 10)}</text><text className="chart-tooltip-price" x="10" y="40">{formatMoney(selected.equity)}</text></g></g>}
      </svg>
      <div className="chart-explorer"><label htmlFor={slider}>Explore recorded snapshots</label><input id={slider} type="range" min="0" max={snapshots.length - 1} step="1" value={selectedIndex} aria-valuetext={`${selected.taken_at}, equity ${formatMoney(selected.equity)} virtual USD`} onChange={(event) => setIndex(Number(event.target.value))} onFocus={() => setIndex(selectedIndex)} onBlur={() => setIndex(null)} /><span className="muted">Arrow keys or drag · {snapshots.length} recorded observations · UTC dates</span></div>
      {snapshots.length === 1 && <p className="chart-provenance" role="status">One snapshot recorded. More observations are needed to show a trend.</p>}
      <p className="chart-provenance">Actual paper portfolio snapshots valued at completed daily closes. Gaps are not filled. Equity includes deposits; the return metrics exclude them.</p>
    </div>
  );
}

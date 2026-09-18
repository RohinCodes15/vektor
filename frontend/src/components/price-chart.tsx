"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { MarketHistoryResponse } from "../lib/api";
import { formatChartPrice, nearestChartPoint, priceChartGeometry } from "../lib/price-chart";

export function PriceChart({ history }: { history: MarketHistoryResponse }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const instructions = useId();
  const geometry = useMemo(() => priceChartGeometry(history.bars, width), [history.bars, width]);
  const active = activeIndex === null ? null : geometry.points[activeIndex];
  const latest = history.bars.at(-1);

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(160, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  if (!latest) return <p className="chart-state" role="status">No daily prices in this date range.</p>;
  const selected = active ?? latest;
  const tooltipX = active ? Math.max(4, Math.min(active.x - 70, width - 144)) : 0;

  return (
    <div className="price-chart" ref={container}>
      <div className="chart-price"><div><span className="eyebrow">DAILY CLOSE / {history.currency ?? "CURRENCY UNSPECIFIED"}</span><p>{formatChartPrice(selected.close)}</p></div><span className="mono muted text-xs">{selected.date}<br />Historical close, not a live quote</span></div>
      <svg className="price-plot" width="100%" height="280" viewBox={`0 0 ${width} 280`} role="img" aria-label={`${history.symbol} daily closing prices, ${history.bars[0].date} to ${latest.date}`} onPointerMove={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        setActiveIndex(nearestChartPoint(geometry.points, ((event.clientX - bounds.left) / bounds.width) * width));
      }} onPointerDown={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        setActiveIndex(nearestChartPoint(geometry.points, ((event.clientX - bounds.left) / bounds.width) * width));
      }} onPointerLeave={() => setActiveIndex(null)} onPointerCancel={() => setActiveIndex(null)}>
        <desc>Unadjusted daily closing prices. Missing trading days are not filled. Use the trading-day slider below for keyboard access to every observation.</desc>
        {geometry.priceTicks.map((tick, index) => <g key={index}><line className="chart-grid-line" x1={geometry.plot.left} x2={geometry.plot.right} y1={tick.y} y2={tick.y} /><text className="chart-axis-label" x={geometry.plot.left - 10} y={tick.y + 4} textAnchor="end">{formatChartPrice(tick.value)}</text></g>)}
        {geometry.dateTicks.map((tick, index) => <text key={tick.date} className="chart-axis-label" x={tick.x} y={266} textAnchor={geometry.dateTicks.length === 1 ? "middle" : index === 0 ? "start" : index === geometry.dateTicks.length - 1 ? "end" : "middle"}>{tick.date}</text>)}
        <path className="chart-price-line" d={geometry.path} />
        {geometry.points.length === 1 && <circle className="chart-point" cx={geometry.points[0].x} cy={geometry.points[0].y} r="4" />}
        {active && <g className="chart-crosshair" aria-hidden="true"><line x1={active.x} x2={active.x} y1={geometry.plot.top} y2={geometry.plot.bottom} /><circle className="chart-point" cx={active.x} cy={active.y} r="4" /><g transform={`translate(${tooltipX},28)`}><rect className="chart-tooltip-bg" width="140" height="52" rx="5" /><text x="10" y="20">{active.date}</text><text className="chart-tooltip-price" x="10" y="40">{formatChartPrice(active.close)}</text></g></g>}
      </svg>
      <div className="chart-explorer"><label htmlFor={instructions}>Explore trading days</label><input id={instructions} type="range" min="0" max={history.bars.length - 1} step="1" value={activeIndex ?? history.bars.length - 1} aria-describedby={`${instructions}-help`} aria-valuetext={`${selected.date}, close ${formatChartPrice(selected.close)} ${history.currency ?? "currency unspecified"}`} onChange={(event) => setActiveIndex(Number(event.target.value))} onFocus={() => setActiveIndex((index) => index ?? history.bars.length - 1)} onBlur={() => setActiveIndex(null)} /><span id={`${instructions}-help`} className="muted">Arrow keys or drag · {history.bars.length} observations</span></div>
      <p className="chart-provenance">Yahoo Finance · {history.cached ? "Cached history" : "Provider history"} · Fetched <time dateTime={history.fetched_at}>{new Date(history.fetched_at).toLocaleString()}</time></p>
    </div>
  );
}

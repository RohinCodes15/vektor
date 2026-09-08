"use client";

import { useState } from "react";
import type { PortfolioAllocation } from "../lib/api";
import { formatMoney } from "../lib/portfolio-values";

const colors = ["#59c9b5", "#a6a3ef", "#e4b86c", "#72b7e5", "#e693ae", "#a7c57c"];

export function AllocationDonut({ allocation }: { allocation: PortfolioAllocation }) {
  const [active, setActive] = useState("cash");
  const segments = [
    { id: "cash", label: "Cash", weight: allocation.cash_weight_pct, value: allocation.cash },
    ...allocation.assets.map((asset) => ({ id: `asset:${asset.symbol}`, label: asset.symbol, weight: asset.weight_pct, value: asset.market_value })),
  ];
  const selected = segments.find((segment) => segment.id === active) ?? segments[0];
  const drawable = segments.every((segment) => segment.weight !== null);
  const total = segments.reduce((sum, segment) => sum + Number(segment.weight ?? 0), 0);
  if (!drawable || total <= 0) return <div className="chart-state" role="status"><h3>Allocation chart unavailable</h3><p>{allocation.unavailable_reason ?? "Equity weights are unavailable."}</p></div>;
  let offset = 0;
  return (
    <div className="allocation-donut">
      <svg viewBox="0 0 240 240" role="group" aria-label="Portfolio allocation donut including cash">
        {segments.map((segment, index) => {
          // Normalize rounded weights for SVG geometry only; displayed weights remain the API values.
          const size = Number(segment.weight) / total * 100;
          const start = offset; offset += size;
          return size === 0 ? null : <circle key={segment.id} className={`donut-segment ${selected.id === segment.id ? "donut-active" : ""}`} cx="120" cy="120" r="85" fill="none" stroke={colors[index % colors.length]} strokeWidth="30" pathLength="100" strokeDasharray={`${size} ${100 - size}`} strokeDashoffset={-start} transform="rotate(-90 120 120)" role="button" tabIndex={0} aria-pressed={selected.id === segment.id} aria-label={`${segment.label}: ${segment.weight}% of equity, ${formatMoney(segment.value)}`} onPointerEnter={() => setActive(segment.id)} onFocus={() => setActive(segment.id)} onClick={() => setActive(segment.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setActive(segment.id); } }}><title>{segment.label}: {segment.weight}% · {formatMoney(segment.value)}</title></circle>;
        })}
        <text x="120" y="110" textAnchor="middle" className="donut-label" aria-hidden="true">{selected.label}</text><text x="120" y="139" textAnchor="middle" className="donut-value" aria-hidden="true">{selected.weight}%</text>
      </svg>
      <p className="allocation-tooltip" role="status" aria-live="polite">{selected.label} · {selected.weight}% of equity · {formatMoney(selected.value)}</p>
      <div className="allocation-legend" aria-label="Select allocation asset">{segments.map((segment, index) => <button type="button" key={segment.id} aria-pressed={selected.id === segment.id} onClick={() => setActive(segment.id)}><span className="allocation-swatch" style={{ background: colors[index % colors.length] }} aria-hidden="true" />{segment.label}<span>{segment.weight}%</span></button>)}</div>
      <p className="chart-provenance">Weights include cash. Rounded API weights can differ slightly from 100%.</p>
    </div>
  );
}

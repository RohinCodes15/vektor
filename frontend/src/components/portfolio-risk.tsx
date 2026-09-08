"use client";

import { useState } from "react";
import type { PortfolioRisk } from "../lib/api";
import { Badge, Panel } from "./ui";

export function RiskContribution({ risk }: { risk: PortfolioRisk }) {
  const [active, setActive] = useState<string | null>(null);
  const measured = risk.assets.filter((asset) => asset.volatility_contribution_pct !== null);
  const maximum = Math.max(...measured.map((asset) => Math.abs(Number(asset.volatility_contribution_pct))), 0);
  const selected = risk.assets.find((asset) => asset.symbol === active);
  if (measured.length === 0) return <div className="chart-state" role="status"><h3>Risk contributions unavailable</h3><p>Contributions are undefined when portfolio volatility is zero. No contribution values are estimated.</p></div>;
  return <>
    <p className="chart-provenance">Annualized volatility contributions in percentage points. Negative contributions hedge other holdings. Cash has zero variance and is included in equity weights.</p>
    <div className="holdings-scroll" role="region" aria-label="Risk contribution chart" tabIndex={0}><svg className="risk-bars" viewBox={`0 0 600 ${risk.assets.length * 44 + 28}`} role="group" aria-label="Asset contributions to annualized portfolio volatility"><line className="chart-grid-line" x1="330" x2="330" y1="0" y2={risk.assets.length * 44} />{risk.assets.map((asset, index) => {
      const contribution = asset.volatility_contribution_pct;
      const length = maximum === 0 ? 0 : Math.abs(Number(contribution)) / maximum * 170;
      const x = Number(contribution) < 0 ? 330 - length : 330;
      return <g key={asset.symbol} className="risk-bar" tabIndex={0} role="img" aria-label={`${asset.symbol}, ${contribution === null ? "unavailable" : `${contribution} volatility points`}, share ${asset.contribution_share_pct ?? "unavailable"}${asset.contribution_share_pct === null ? "" : "%"}`} onPointerEnter={() => setActive(asset.symbol)} onFocus={() => setActive(asset.symbol)}><title>{asset.symbol}: {contribution ?? "Unavailable"} volatility points</title><text className="chart-axis-label" x="12" y={index * 44 + 24}>{asset.symbol}</text>{contribution !== null && <rect x={x} y={index * 44 + 8} width={Math.max(length, 1)} height="24" rx="3" className={Number(contribution) < 0 ? "risk-negative" : "risk-positive"} />}<text className="chart-axis-label" x="510" y={index * 44 + 24}>{contribution ?? "N/A"}</text></g>;
    })}<text className="chart-axis-label" x="330" y={risk.assets.length * 44 + 20} textAnchor="middle">0 volatility points</text></svg></div>
    <p className="allocation-tooltip" role="status" aria-live="polite">{selected ? `${selected.symbol} · Contribution ${selected.volatility_contribution_pct ?? "Unavailable"} points · Share ${selected.contribution_share_pct === null ? "Unavailable" : `${selected.contribution_share_pct}%`}` : "Focus or hover over an asset to inspect its contribution."}</p>
    <div className="holdings-scroll" role="region" aria-label="Risk contribution values" tabIndex={0}><table className="holdings-table"><caption className="muted">Backend risk contributions · Annualized</caption><thead><tr><th scope="col">Asset</th><th scope="col">Equity weight</th><th scope="col">Asset volatility</th><th scope="col">Contribution (points)</th><th scope="col">Contribution share</th></tr></thead><tbody>{risk.assets.map((asset) => <tr key={asset.symbol}><th scope="row">{asset.symbol}</th><td>{asset.weight_pct}%</td><td>{asset.volatility_pct}%</td><td>{asset.volatility_contribution_pct ?? "Unavailable"}</td><td>{asset.contribution_share_pct === null ? "Unavailable" : `${asset.contribution_share_pct}%`}</td></tr>)}</tbody></table></div>
  </>;
}

export function CorrelationHeatmap({ risk }: { risk: PortfolioRisk }) {
  const [active, setActive] = useState("Focus or hover over a correlation to inspect its value.");
  const pairs = new Map(risk.correlations.map((pair) => [`${pair.symbol_a}:${pair.symbol_b}`, pair.correlation]));
  if (risk.correlations.length === 0) return <p className="chart-state" role="status">No correlation observations were provided.</p>;
  return <><div className="holdings-scroll" role="region" aria-label="Asset correlation heatmap" tabIndex={0}><table className="holdings-table correlation-table"><caption className="muted">Pearson correlations · −1 inverse, 0 uncorrelated, +1 aligned · Unavailable cells are never inferred</caption><thead><tr><th scope="col">Asset</th>{risk.assets.map((asset) => <th scope="col" key={asset.symbol}>{asset.symbol}</th>)}</tr></thead><tbody>{risk.assets.map((row) => <tr key={row.symbol}><th scope="row">{row.symbol}</th>{risk.assets.map((column) => {
    const direct = `${row.symbol}:${column.symbol}`;
    const reverse = `${column.symbol}:${row.symbol}`;
    const value = (pairs.has(direct) ? pairs.get(direct) : pairs.get(reverse)) ?? null;
    const label = `${row.symbol} / ${column.symbol}: ${value === null ? "Unavailable (constant series or no reported pair)" : value}`;
    const intensity = value === null ? 0 : 0.2 + Math.abs(Number(value)) * 0.6;
    return <td key={column.symbol} tabIndex={0} title={label} aria-label={label} onFocus={() => setActive(label)} onPointerEnter={() => setActive(label)} style={{ backgroundColor: value === null ? undefined : Number(value) < 0 ? `rgb(93 64 132 / ${intensity})` : `rgb(0 94 85 / ${intensity})` }}>{value ?? "Unavailable"}</td>;
  })}</tr>)}</tbody></table></div><p className="allocation-tooltip" role="status" aria-live="polite">{active}</p></>;
}

export function PortfolioRiskView({ risk }: { risk: PortfolioRisk }) {
  return <Panel className="allocation-panel" aria-labelledby="risk-title"><div className="panel-heading"><div><h3 id="risk-title">Correlation & risk contribution</h3><p className="muted text-xs">Current holdings · Adjusted daily returns</p></div><Badge>{risk.status === "available" ? "Aligned returns" : "Risk unavailable"}</Badge></div><p className="chart-provenance">{risk.window_start} – {risk.window_end} · {risk.observations} aligned returns / {risk.min_observations} minimum · Returns as of {risk.returns_as_of ?? "Unavailable"} · Valued {risk.valued_at}</p>
    {risk.status === "unavailable" ? <div className="chart-state" role="status"><h3>Risk data unavailable</h3><p>{risk.unavailable_reason}</p></div> : <><p className="portfolio-warning">Portfolio volatility: {risk.portfolio_volatility_pct}% annualized</p><h4>Risk contribution</h4><RiskContribution risk={risk} /><h4>Correlation heatmap</h4><CorrelationHeatmap risk={risk} /></>}
    <p className="chart-provenance">Risk assumes today’s quantities were held throughout the window; it is not realized portfolio performance. √252 annualization. Missing aligned observations are not filled.</p>
  </Panel>;
}

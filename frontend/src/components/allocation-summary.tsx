import type { PortfolioAllocation } from "../lib/api";
import { formatMoney } from "../lib/portfolio-values";
import { AllocationDonut } from "./allocation-donut";
import { Badge, MetricCard, Panel } from "./ui";

export function AllocationSummary({ allocation }: { allocation: PortfolioAllocation }) {
  return <>
    <div className="metrics-grid allocation-metrics"><MetricCard label="Top holding concentration" value={allocation.top_holding_pct === null ? "Unavailable" : `${allocation.top_holding_pct}%`} detail={allocation.top_holding_symbol ? `${allocation.top_holding_symbol} · Share of invested positions, cash excluded` : "No priced positions to measure"} /><MetricCard label="HHI concentration" value={allocation.hhi ?? "Unavailable"} detail="Sum of squared position weights · Cash excluded · Higher means more concentrated" /></div>
    <Panel className="allocation-panel" aria-labelledby="allocation-title"><div className="panel-heading"><div><h3 id="allocation-title">Portfolio allocation</h3><p className="muted text-xs">Virtual USD · Latest completed closes</p></div><Badge>{allocation.status === "available" ? "Current weights" : "Partial availability"}</Badge></div>
      <p className="chart-provenance">Valued <time dateTime={allocation.valued_at}>{allocation.valued_at}</time> · Oldest price {allocation.prices_as_of ?? "Unavailable / cash only"}</p>
      {allocation.status === "unavailable" && <p className="portfolio-warning" role="status">{allocation.unavailable_reason}</p>}
      {allocation.stale_symbols.length > 0 && <p className="portfolio-warning" role="status">Stale closes (older than four calendar days): {allocation.stale_symbols.join(", ")}. Weights use those actual closes.</p>}
      {allocation.unpriced_symbols.length > 0 && <p className="portfolio-warning" role="status">Unpriced holdings: {allocation.unpriced_symbols.join(", ")}. No partial weights are estimated.</p>}
      <div className="allocation-layout"><AllocationDonut allocation={allocation} /><div className="holdings-scroll" role="region" aria-label="Position weights including cash" tabIndex={0}><table className="holdings-table"><caption className="muted">Position weights · Equity includes cash; position weights exclude cash</caption><thead><tr><th scope="col">Asset</th><th scope="col">Quantity</th><th scope="col">Value (USD)</th><th scope="col">Equity weight</th><th scope="col">Position weight</th><th scope="col">Price date</th></tr></thead><tbody><tr><th scope="row">Cash</th><td>—</td><td>{formatMoney(allocation.cash)}</td><td>{allocation.cash_weight_pct === null ? "Unavailable" : `${allocation.cash_weight_pct}%`}</td><td>Not applicable</td><td>Not applicable</td></tr>{allocation.assets.map((asset) => <tr key={asset.symbol}><th scope="row">{asset.symbol}{asset.stale && <Badge tone="warning">Stale</Badge>}</th><td>{asset.quantity}</td><td>{formatMoney(asset.market_value)}</td><td>{asset.weight_pct === null ? "Unavailable" : `${asset.weight_pct}%`}</td><td>{asset.position_weight_pct === null ? "Unavailable" : `${asset.position_weight_pct}%`}</td><td>{asset.price_date ?? "Unavailable"}</td></tr>)}</tbody></table>{allocation.assets.length === 0 && <p className="chart-provenance" role="status">No open positions. Available cash remains visible above.</p>}</div></div>
    </Panel>
  </>;
}

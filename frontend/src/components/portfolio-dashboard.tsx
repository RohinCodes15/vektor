"use client";

import { useCallback, useEffect, useState } from "react";
import { getPortfolios, getPortfolioHoldings, type Portfolio, type PortfolioHoldings } from "../lib/api";
import { formatMoney, formatTotalPnl } from "../lib/portfolio-values";
import { TransactionHistory } from "./transaction-history";
import { Badge, Button, MetricCard, Panel } from "./ui";

type Remote<T> = { status: "loading" } | { status: "error"; message: string } | { status: "success"; data: T };

export function PortfolioDashboard() {
  const [list, setList] = useState<Remote<readonly Portfolio[]>>({ status: "loading" });
  const [selected, setSelected] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted) return;
      try {
        const data = await getPortfolios(controller.signal);
        if (!controller.signal.aborted) setList({ status: "success", data });
      } catch (error) {
        if (!controller.signal.aborted) setList({ status: "error", message: error instanceof Error ? error.message : "Portfolio list unavailable." });
      }
    });
    return () => controller.abort();
  }, [revision]);
  function refresh(): void { setList({ status: "loading" }); setRevision((value) => value + 1); }
  const portfolio = list.status === "success" ? list.data.find((item) => item.id === selected) ?? list.data[0] : undefined;

  return (
    <div className="portfolio-dashboard" aria-busy={list.status === "loading"}>
      <div className="section-heading"><div><span className="eyebrow">01 / YOUR CAPITAL, SIMULATED</span><h2>Portfolio overview</h2></div><Badge>Virtual USD · Paper only</Badge></div>
      {list.status === "loading" && <Panel className="chart-state"><p role="status">Loading paper portfolios…</p></Panel>}
      {list.status === "error" && <Panel className="chart-state"><h3>Portfolios unavailable</h3><p role="alert">{list.message}</p><Button variant="secondary" onClick={refresh}>Retry portfolios</Button></Panel>}
      {list.status === "success" && !portfolio && <Panel className="chart-state"><h3>No paper portfolios yet.</h3><p>Create a portfolio through the local portfolio API to see its virtual cash and holdings here.</p><Button variant="secondary" onClick={refresh}>Refresh portfolios</Button></Panel>}
      {portfolio && <>
        <div className="portfolio-controls"><div className="field"><label htmlFor="portfolio-select">Paper portfolio</label><select id="portfolio-select" value={portfolio.id} onChange={(event) => setSelected(event.target.value)}>{list.status === "success" && list.data.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div><Button variant="secondary" onClick={refresh}>Refresh portfolios</Button></div>
        <PortfolioDetails key={`${portfolio.id}:${revision}`} id={portfolio.id} />
      </>}
    </div>
  );
}

export function PortfolioDetails({ id }: { id: string }) {
  const [state, setState] = useState<Remote<PortfolioHoldings>>({ status: "loading" });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted) return;
      try {
        const data = await getPortfolioHoldings(id, controller.signal);
        if (!controller.signal.aborted) setState({ status: "success", data });
      } catch (error) {
        if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "Portfolio valuation unavailable." });
      }
    });
    return () => controller.abort();
  }, [id, revision]);
  const refreshAfterTrades = useCallback(() => { setState({ status: "loading" }); setRevision((value) => value + 1); }, []);
  const data = state.status === "success" ? state.data : null;
  return (
    <div aria-busy={state.status === "loading"}>
      <div className="metrics-grid">
        <MetricCard label="Portfolio value" value={data ? formatMoney(data.equity) : "—"} detail="Cash + holdings at completed daily closes" />
        <MetricCard label="Available cash" value={data ? formatMoney(data.cash) : "—"} detail="Virtual USD available for paper orders" />
        <MetricCard label="Total P&L" value={data ? formatTotalPnl(data.realized_pnl, data.unrealized_pnl) : "—"} detail="Realized + unrealized profit and loss" />
        <MetricCard label="Open positions" value={data ? String(data.holdings.length) : "—"} detail="Holdings in this paper portfolio" />
      </div>
      <Panel className="holdings-panel" aria-labelledby="holdings-title">
        <div className="panel-heading"><h3 id="holdings-title">Holdings</h3><Badge>Daily closes · Not live</Badge></div>
        {state.status === "loading" && <p className="chart-state" role="status">Loading portfolio valuation…</p>}
        {state.status === "error" && <div className="chart-state"><h3>Valuation unavailable</h3><p role="alert">{state.message}</p><Button variant="secondary" onClick={() => { setState({ status: "loading" }); setRevision((value) => value + 1); }}>Retry valuation</Button></div>}
        {data && <>
          <p className="muted text-xs">Valued at <time dateTime={data.valued_at}>{data.valued_at}</time>. Prices may have different trading dates.</p>
          {data.equity === null && <p className="portfolio-warning" role="status">Some holdings have no recent price. Portfolio value and total P&L are unavailable; balances are never estimated.</p>}
          {data.holdings.length === 0 ? <div className="chart-state"><h3>No open holdings.</h3><p>This portfolio currently holds virtual cash only.</p></div> :
            <div className="holdings-scroll" role="region" aria-label="Portfolio holdings" tabIndex={0}><table className="holdings-table"><caption className="muted">Paper positions · USD · Unpriced values are unavailable</caption><thead><tr><th scope="col">Symbol</th><th scope="col">Quantity</th><th scope="col">Cost basis</th><th scope="col">Market value</th><th scope="col">Unrealized P&L</th><th scope="col">Price date</th></tr></thead><tbody>{data.holdings.map((holding) => <tr key={holding.symbol}><th scope="row">{holding.symbol}</th><td>{holding.quantity}</td><td>{formatMoney(holding.cost_basis)}</td><td>{formatMoney(holding.market_value)}</td><td>{formatMoney(holding.unrealized_pnl)}</td><td>{holding.price_date ?? "Unavailable"}</td></tr>)}</tbody></table></div>}
        </>}
      </Panel>
      <TransactionHistory id={id} onTrades={refreshAfterTrades} />
    </div>
  );
}

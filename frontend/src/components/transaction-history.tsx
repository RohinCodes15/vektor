"use client";

import { useEffect, useRef, useState } from "react";
import { getPortfolioTransactions, type Transaction } from "../lib/api";
import { formatMoney } from "../lib/portfolio-values";
import { Badge, Button, Panel } from "./ui";

type HistoryState = { status: "loading" } | { status: "success"; data: readonly Transaction[] } | { status: "error"; message: string };

export function TransactionHistory({ id, onTrades }: { id: string; onTrades: () => void }) {
  const [state, setState] = useState<HistoryState>({ status: "loading" });
  const [busy, setBusy] = useState(true);
  const previous = useRef<{ id: string; signature: string } | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let stopped = false;
    let pending = false;
    let controller: AbortController;
    async function load(): Promise<void> {
      if (stopped || pending) return;
      pending = true;
      controller = new AbortController();
      setBusy(true);
      try {
        const data = await getPortfolioTransactions(id, controller.signal);
        if (stopped) return;
        const signature = data.map((item) => item.id).join(",");
        setState({ status: "success", data });
        if (previous.current?.id === id && previous.current.signature !== signature) onTrades();
        previous.current = { id, signature };
      } catch (error) {
        if (!stopped) setState({ status: "error", message: error instanceof Error ? error.message : "Transaction history unavailable." });
      } finally {
        pending = false;
        if (!stopped) setBusy(false);
      }
    }
    function refreshVisible(): void { if (document.visibilityState !== "hidden") void load(); }
    void Promise.resolve().then(() => load());
    const timer = window.setInterval(refreshVisible, 15000);
    window.addEventListener("focus", refreshVisible);
    return () => { stopped = true; controller?.abort(); window.clearInterval(timer); window.removeEventListener("focus", refreshVisible); };
  }, [id, onTrades, revision]);

  return (
    <Panel className="holdings-panel transaction-panel" aria-labelledby="transactions-title" aria-busy={busy}>
      <div className="panel-heading"><div><h3 id="transactions-title">Transaction history</h3><p className="muted text-xs">Paper trades · Virtual USD · Refreshes every 15 seconds while visible</p></div><Button variant="secondary" disabled={busy} onClick={() => setRevision((value) => value + 1)}>{busy ? "Refreshing…" : "Refresh trades"}</Button></div>
      {state.status === "loading" && <p className="chart-state" role="status">Loading paper trades…</p>}
      {state.status === "error" && <div className="chart-state"><h3>Trade history unavailable</h3><p role="alert">{state.message}</p><Button variant="secondary" disabled={busy} onClick={() => setRevision((value) => value + 1)}>Retry trades</Button></div>}
      {state.status === "success" && (state.data.length === 0 ? <div className="chart-state" role="status"><h3>No paper trades yet.</h3><p>Executed paper orders for this portfolio will appear here.</p></div> :
        <div className="holdings-scroll" role="region" aria-label="Paper transaction history" tabIndex={0}><table className="holdings-table"><caption className="muted">Executed paper trades · Oldest first · Prices are completed daily closes</caption><thead><tr><th scope="col">Ticker</th><th scope="col">Side</th><th scope="col">Quantity</th><th scope="col">Execution price</th><th scope="col">Total</th><th scope="col">Executed (UTC)</th><th scope="col">Price date</th></tr></thead><tbody>{state.data.map((trade) => <tr key={trade.id}><th scope="row">{trade.symbol}</th><td><Badge tone={trade.side === "buy" ? "positive" : "neutral"}>{trade.side === "buy" ? "Buy" : "Sell"}</Badge></td><td>{trade.quantity}</td><td>${trade.price}</td><td>{formatMoney(trade.notional)}</td><td><time dateTime={trade.executed_at}>{`${new Date(trade.executed_at).toISOString().slice(0, 19).replace("T", " ")} UTC`}</time></td><td><time dateTime={trade.price_date}>{trade.price_date}</time></td></tr>)}</tbody></table></div>)}
    </Panel>
  );
}

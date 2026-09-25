"use client";

import { useState } from "react";
import { useMarketHistory } from "../hooks/use-market-history";
import { PriceChart } from "./price-chart";
import { Button, Field } from "./ui";

export function StockHistory({ symbol }: { symbol: string }) {
  const { state, load } = useMarketHistory();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const noData = (state.status === "success" && state.data.bars.length === 0) || (state.status === "error" && state.statusCode === 404);

  return (
    <div className="stock-history">
      <form className="history-form" onSubmit={(event) => { event.preventDefault(); void load({ symbol, start, end }); }}>
        <Field id={`history-start-${symbol}`} label="Start date" type="date" value={start} disabled={state.status === "loading"} required onChange={(event) => setStart(event.target.value)} />
        <Field id={`history-end-${symbol}`} label="End date" type="date" value={end} disabled={state.status === "loading"} min={start || undefined} required onChange={(event) => setEnd(event.target.value)} />
        <Button type="submit" variant="secondary" disabled={state.status === "loading"}>{state.status === "loading" ? "Loading…" : "Load history"}</Button>
        <p className="history-hint muted">Inclusive dates · Daily close · No live quotes</p>
      </form>
      <p role="status" aria-live="polite" className="history-status">{state.status === "loading" ? `Loading ${symbol} historical prices…` : state.status === "success" ? `${state.data.bars.length} daily observations loaded for ${symbol}.` : state.status === "idle" ? "Choose a date range to load historical prices." : noData ? `No daily observations found for ${symbol}.` : ""}</p>
      <div aria-busy={state.status === "loading"}>
        {state.status === "idle" && <div className="chart-state"><span className="empty-icon" aria-hidden="true">⌁</span><h3>A closer look at the history.</h3><p>Choose inclusive start and end dates above.<br />Historical daily closes load on demand.</p></div>}
        {state.status === "loading" && <div className="chart-state"><p>Fetching daily closing prices.</p></div>}
        {state.status === "error" && !noData && <div className="chart-state" role="alert"><h3>History unavailable</h3><p>{state.message}</p><Button type="button" variant="secondary" onClick={() => void load({ symbol, start, end })}>Retry history</Button></div>}
        {noData && <div className="chart-state"><h3>No observations in this range.</h3><p>Try another date range or symbol.</p></div>}
        {state.status === "success" && !noData && <><p className="history-loaded-range muted">Showing {state.data.symbol} · {state.data.start} – {state.data.end} · Daily close</p><PriceChart history={state.data} /></>}
      </div>
    </div>
  );
}

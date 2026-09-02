"use client";

import { useEffect, useState } from "react";
import { historyRange, type HistoryRange } from "../lib/history-range";
import { useMarketHistory } from "../hooks/use-market-history";
import { PriceChart } from "./price-chart";
import { Button, Field } from "./ui";

export function StockHistory({ symbol }: { symbol: string }) {
  const { state: result, load } = useMarketHistory();
  const [range, setRange] = useState<HistoryRange | null>("1Y");
  const [start, setStart] = useState(() => historyRange("1Y").start);
  const [end, setEnd] = useState(() => historyRange("1Y").end);
  const [dates, setDates] = useState(() => historyRange("1Y"));
  useEffect(() => { void load({ symbol, ...dates }); }, [symbol, dates, load]);
  const current = result.status === "idle" || (result.status === "success"
    ? result.data.symbol === symbol && result.data.start === dates.start && result.data.end === dates.end
    : result.query.symbol === symbol && result.query.start === dates.start && result.query.end === dates.end);
  const state = current ? result : { status: "loading" as const, query: { symbol, ...dates } };

  const noData = (state.status === "success" && state.data.bars.length === 0) || (state.status === "error" && state.statusCode === 404);

  return (
    <div className="stock-history">
      <div className="history-ranges" role="group" aria-label="History time range">
        {(["1M", "3M", "6M", "1Y", "ALL"] as const).map((value) => <Button key={value} type="button" variant={range === value ? "primary" : "secondary"} aria-pressed={range === value} onClick={() => {
          const next = historyRange(value);
          setRange(value); setStart(next.start); setEnd(next.end); setDates((current) => current.start === next.start && current.end === next.end ? current : next);
        }}>{value}</Button>)}
      </div>
      <form className="history-form" onSubmit={(event) => { event.preventDefault(); setRange(null); setDates((current) => current.start === start && current.end === end ? current : { start, end }); }}>
        <Field id={`history-start-${symbol}`} label="Start date" type="date" value={start} disabled={state.status === "loading"} required onChange={(event) => setStart(event.target.value)} />
        <Field id={`history-end-${symbol}`} label="End date" type="date" value={end} disabled={state.status === "loading"} min={start || undefined} required onChange={(event) => setEnd(event.target.value)} />
        <Button type="submit" variant="secondary" disabled={state.status === "loading"}>{state.status === "loading" ? "Loading…" : "Load history"}</Button>
        <p className="history-hint muted">Inclusive dates · Daily close · No live quotes · ALL requests history since 1900</p>
      </form>
      <p role="status" aria-live="polite" className="history-status">{state.status === "loading" ? `Loading ${symbol} historical prices…` : state.status === "success" ? `${state.data.bars.length} daily observations loaded for ${symbol}.` : state.status === "idle" ? "Historical daily closes load on demand." : noData ? `No daily observations found for ${symbol}.` : ""}</p>
      <div aria-busy={state.status === "loading"}>
        {state.status === "idle" && <div className="chart-state"><span className="empty-icon" aria-hidden="true">⌁</span><h3>A closer look at the history.</h3><p>Choose inclusive start and end dates above.<br />Historical daily closes load on demand.</p></div>}
        {state.status === "loading" && <div className="chart-state"><p>Fetching daily closing prices.</p></div>}
        {state.status === "error" && !noData && <div className="chart-state" role="alert"><h3>History unavailable</h3><p>{state.message}</p><Button type="button" variant="secondary" onClick={() => void load({ symbol, ...dates })}>Retry history</Button></div>}
        {noData && <div className="chart-state"><h3>No observations in this range.</h3><p>Check the ticker or try another date range.</p></div>}
        {state.status === "success" && !noData && <><p className="history-loaded-range muted">Showing {state.data.symbol} · {state.data.start} – {state.data.end} · Daily close</p><PriceChart key={`${state.data.symbol}:${state.data.start}:${state.data.end}`} history={state.data} /></>}
      </div>
    </div>
  );
}

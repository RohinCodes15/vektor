"use client";

import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { StockHistory } from "./stock-history";
import { Badge, Button, Field, Panel } from "./ui";

// Reference metadata only; prices and market status require a real data source.
const symbols = [
  { symbol: "AAPL", name: "Apple Inc.", sector: "Technology", exchange: "NASDAQ" },
  { symbol: "MSFT", name: "Microsoft Corporation", sector: "Technology", exchange: "NASDAQ" },
  { symbol: "NVDA", name: "NVIDIA Corporation", sector: "Technology", exchange: "NASDAQ" },
  { symbol: "SPY", name: "SPDR S&P 500 ETF Trust", sector: "Index ETF", exchange: "NYSE Arca" },
] as const;

export function MarketWorkspace() {
  const reduced = useReducedMotion();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<(typeof symbols)[number]>(symbols[0]);
  const matches = symbols.filter(({ symbol, name }) => `${symbol} ${name}`.toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <section id="market" aria-labelledby="market-title">
      <div className="section-heading"><div><span className="eyebrow">02 / EXPLORE</span><h2 id="market-title">Market workspace</h2></div><Badge>Historical data · Not live</Badge></div>
      <div className="market-grid">
        <Panel className="watchlist" aria-labelledby="watchlist-title">
          <div className="panel-heading"><h3 id="watchlist-title">Reference symbols</h3><span className="mono muted text-xs">04</span></div>
          <Field id="symbol-search" label="Find a symbol" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search symbol or company" autoComplete="off" hint="Choose a symbol, then load its historical daily prices. No live quotes." />
          <div className="watchlist-heading" aria-hidden="true"><span>INSTRUMENT</span><span>LIVE QUOTE</span></div>
          <ul className="symbol-list" aria-label="Reference symbols">
            {matches.map((item) => <li key={item.symbol}><button type="button" className={`symbol-row ${selected.symbol === item.symbol ? "symbol-selected" : ""}`} aria-pressed={selected.symbol === item.symbol} aria-controls="instrument-details" onClick={() => setSelected(item)}><span className="symbol-monogram" aria-hidden="true">{item.symbol.slice(0, 1)}</span><span className="symbol-name"><strong>{item.symbol}</strong><span>{item.name}</span></span><span className="quote-unavailable">Unavailable</span></button></li>)}
          </ul>
          <p role="status" className="search-result muted">{matches.length === 0 ? "No matching symbols. Try another name or ticker." : `${matches.length} reference ${matches.length === 1 ? "symbol" : "symbols"}`}</p>
        </Panel>
        <Panel id="instrument-details" className="instrument" aria-labelledby="instrument-title">
          <div className="panel-heading"><div aria-live="polite" aria-atomic="true"><motion.div key={selected.symbol} className="instrument-heading" initial={false} animate={{ y: reduced ? 0 : [2, 0] }}><span className="instrument-mark" aria-hidden="true">{selected.symbol.slice(0, 1)}</span><div><h3 id="instrument-title">{selected.symbol}</h3><p className="muted text-xs">{selected.name}</p></div></motion.div></div><Badge>Daily close</Badge></div>
          <div className="instrument-meta"><span>{selected.exchange}</span><span>{selected.sector}</span></div>
          <StockHistory key={selected.symbol} symbol={selected.symbol} />
          <div className="instrument-footer"><span className="muted text-xs">Historical prices only. No live quotes.</span><Button variant="secondary" disabled>Paper order · Coming soon</Button></div>
        </Panel>
      </div>
    </section>
  );
}

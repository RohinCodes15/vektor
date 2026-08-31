"use client";

import { useMemo, useState } from "react";
import type { BacktestTrade } from "../lib/api";
import { formatMoney } from "../lib/portfolio-values";
import { Badge, Panel } from "./ui";

type SortKey = "fill_date" | "symbol" | "side" | "quantity" | "price" | "fee" | "realized_pnl";
type Direction = "ascending" | "descending";

const columns: readonly Readonly<{ key: SortKey; label: string }>[] = [
  { key: "fill_date", label: "Date" }, { key: "symbol", label: "Symbol" }, { key: "side", label: "Side" },
  { key: "quantity", label: "Quantity" }, { key: "price", label: "Execution price" }, { key: "fee", label: "Fees" },
  { key: "realized_pnl", label: "P&L" },
];

function compareTrades(left: BacktestTrade, right: BacktestTrade, key: SortKey): number {
  if (key === "quantity") return left.quantity - right.quantity;
  if (key === "price" || key === "fee" || key === "realized_pnl") return Number(left[key] ?? Number.NEGATIVE_INFINITY) - Number(right[key] ?? Number.NEGATIVE_INFINITY);
  return left[key].localeCompare(right[key]);
}

export function BacktestTrades({ trades }: { trades: readonly BacktestTrade[] }) {
  const [sort, setSort] = useState<Readonly<{ key: SortKey; direction: Direction }>>({ key: "fill_date", direction: "ascending" });
  const sorted = useMemo(() => [...trades].sort((left, right) => {
    const result = compareTrades(left, right, sort.key);
    return (sort.direction === "ascending" ? result : -result) || left.fill_date.localeCompare(right.fill_date) || left.symbol.localeCompare(right.symbol);
  }), [sort, trades]);
  function changeSort(key: SortKey): void {
    setSort((current) => ({ key, direction: current.key === key && current.direction === "ascending" ? "descending" : "ascending" }));
  }
  return (
    <Panel className="backtest-trades" aria-labelledby="backtest-trades-title">
      <div className="panel-heading"><div><h3 id="backtest-trades-title">Trade history</h3><p className="muted text-xs">Simulated fills at adjusted daily opens</p></div><Badge>{trades.length} {trades.length === 1 ? "fill" : "fills"}</Badge></div>
      {trades.length === 0 ? <div className="trade-empty" role="status"><span className="empty-icon" aria-hidden="true">↳</span><h3>No trades executed.</h3><p>The strategy produced no fillable orders in this date range.</p></div> : <>
        <p className="trade-scroll-hint muted">Scroll horizontally to view every column on small screens.</p>
        <div className="trade-table-scroll" tabIndex={0} role="region" aria-label="Sortable backtest trade history">
          <table className="backtest-trade-table">
            <caption>{trades.length} simulated {trades.length === 1 ? "fill" : "fills"}. Select a column heading to sort.</caption>
            <thead><tr>{columns.map((column) => <th key={column.key} scope="col" aria-sort={sort.key === column.key ? sort.direction : "none"}><button type="button" onClick={() => changeSort(column.key)}>{column.label}<span aria-hidden="true">{sort.key === column.key ? sort.direction === "ascending" ? " ↑" : " ↓" : " ↕"}</span></button></th>)}</tr></thead>
            <tbody>{sorted.map((trade, index) => <tr key={`${trade.fill_date}:${trade.symbol}:${trade.side}:${index}`}>
              <td><time dateTime={trade.fill_date}>{trade.fill_date}</time></td><td><strong>{trade.symbol}</strong></td><td><Badge tone={trade.side === "buy" ? "positive" : "warning"}>{trade.side.toUpperCase()}</Badge></td>
              <td>{trade.quantity}</td><td className="mono">${trade.price}</td><td className="mono">{formatMoney(trade.fee)}</td><td className={`mono ${trade.realized_pnl !== null && Number(trade.realized_pnl) >= 0 ? "text-teal" : ""}`}>{trade.realized_pnl === null ? <span className="muted" aria-label="Not available">—</span> : formatMoney(trade.realized_pnl)}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </>}
    </Panel>
  );
}

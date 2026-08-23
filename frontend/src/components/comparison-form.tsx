"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { runBacktestComparison, type BacktestComparison, type BacktestStrategy } from "../lib/api";
import { Badge, Button, Field, Panel } from "./ui";

type StrategyRow = Readonly<{
  id: number; kind: BacktestStrategy["kind"]; fast: string; slow: string; period: string; oversold: string; overbought: string;
}>;
export type ComparisonState = { status: "idle" | "loading" } | { status: "error"; message: string }
  | { status: "success"; data: BacktestComparison };
const strategyNames = { buy_and_hold: "Buy & Hold", sma_crossover: "SMA", rsi: "RSI" } as const;
const latestCompletedDate = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

function newRow(id: number, kind: StrategyRow["kind"]): StrategyRow {
  return { id, kind, fast: "20", slow: "50", period: "14", oversold: "30", overbought: "70" };
}

export function ComparisonForm() {
  const [rows, setRows] = useState<readonly StrategyRow[]>([newRow(0, "buy_and_hold"), newRow(1, "sma_crossover")]);
  const nextId = useRef(2);
  const [settings, setSettings] = useState({ symbol: "", start: "", end: "", starting_cash: "10000.00", fee_per_trade: "0.00", fee_bps: "0", slippage_bps: "0" });
  const [state, setState] = useState<ComparisonState>({ status: "idle" });
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  const loading = state.status === "loading";

  function updateRow(id: number, change: Partial<StrategyRow>): void {
    setRows((current) => current.map((row) => row.id === id ? { ...row, ...change } : row));
    setState({ status: "idle" });
  }
  function updateSetting(key: keyof typeof settings, value: string): void {
    setSettings((current) => ({ ...current, [key]: value }));
    setState({ status: "idle" });
  }
  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setState({ status: "loading" });
    const strategies: BacktestStrategy[] = rows.map((row) => row.kind === "buy_and_hold" ? { kind: row.kind }
      : row.kind === "sma_crossover" ? { kind: row.kind, fast_window: Number(row.fast), slow_window: Number(row.slow) }
      : { kind: row.kind, period: Number(row.period), oversold: row.oversold, overbought: row.overbought });
    try {
      const data = await runBacktestComparison({ ...settings, strategies }, controller.signal);
      if (!controller.signal.aborted) setState({ status: "success", data });
    } catch (error) {
      if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "Comparison failed. Try again." });
    } finally {
      pending.current = null;
    }
  }

  return (
    <section id="comparison" className="comparison-section" aria-labelledby="comparison-title">
      <div className="section-heading"><div><span className="eyebrow">COMPARE / CONFIGURE</span><h2 id="comparison-title">Strategy comparison</h2></div><Badge>Paper simulation</Badge></div>
      <Panel className="backtest-panel">
        <form className="backtest-form" onSubmit={submit} aria-busy={loading}>
          <p className="muted text-xs">Choose 2–5 distinct configurations. Strategy 1 is the baseline. All strategies use the same ticker and settings.</p>
          <div className="backtest-fields">
            <Field id="comparison-symbol" label="Shared ticker" value={settings.symbol} onChange={(event) => updateSetting("symbol", event.target.value)} placeholder="AAPL" autoComplete="off" required disabled={loading} />
            <Field id="comparison-start" label="Start date" type="date" value={settings.start} onChange={(event) => updateSetting("start", event.target.value)} max={settings.end || latestCompletedDate} required disabled={loading} />
            <Field id="comparison-end" label="End date" type="date" value={settings.end} onChange={(event) => updateSetting("end", event.target.value)} min={settings.start || undefined} max={latestCompletedDate} required disabled={loading} />
            <Field id="comparison-capital" label="Starting capital (USD)" type="number" min="0.01" max="999999999999.99" step="0.01" value={settings.starting_cash} onChange={(event) => updateSetting("starting_cash", event.target.value)} required disabled={loading} />
          </div>
          <div className="comparison-strategies">{rows.map((row, index) => <fieldset key={row.id} className="comparison-strategy" disabled={loading}>
            <legend>Strategy {index + 1}{index === 0 ? " · Baseline" : ""}</legend>
            <div className="strategy-picker">{(Object.keys(strategyNames) as StrategyRow["kind"][]).map((kind) => <label key={kind}>
              <input type="radio" name={`comparison-kind-${row.id}`} value={kind} checked={row.kind === kind} onChange={() => updateRow(row.id, { kind })} />{strategyNames[kind]}
            </label>)}</div>
            {row.kind === "sma_crossover" && <div className="strategy-fields">
              <Field id={`comparison-fast-${row.id}`} label="Fast window" type="number" min="2" max="250" step="1" value={row.fast} onChange={(event) => updateRow(row.id, { fast: event.target.value })} required />
              <Field id={`comparison-slow-${row.id}`} label="Slow window" type="number" min="3" max="500" step="1" value={row.slow} onChange={(event) => updateRow(row.id, { slow: event.target.value })} required />
            </div>}
            {row.kind === "rsi" && <div className="strategy-fields">
              <Field id={`comparison-period-${row.id}`} label="RSI period" type="number" min="2" max="100" step="1" value={row.period} onChange={(event) => updateRow(row.id, { period: event.target.value })} required />
              <Field id={`comparison-oversold-${row.id}`} label="Oversold" type="number" min="0.01" max="99.99" step="0.01" value={row.oversold} onChange={(event) => updateRow(row.id, { oversold: event.target.value })} required />
              <Field id={`comparison-overbought-${row.id}`} label="Overbought" type="number" min="0.01" max="99.99" step="0.01" value={row.overbought} onChange={(event) => updateRow(row.id, { overbought: event.target.value })} required />
            </div>}
            <Button type="button" variant="ghost" disabled={loading || rows.length <= 2} aria-label={`Remove strategy ${index + 1}`} onClick={() => { setRows((current) => current.filter((item) => item.id !== row.id)); setState({ status: "idle" }); }}>Remove</Button>
          </fieldset>)}</div>
          <Button type="button" variant="secondary" disabled={loading || rows.length >= 5} onClick={() => { const row = newRow(nextId.current++, "rsi"); setRows((current) => [...current, row]); setState({ status: "idle" }); }}>Add strategy</Button>
          <fieldset className="cost-fields" disabled={loading}>
            <legend>Shared trading costs</legend>
            <Field id="comparison-fee" label="Fee per trade (USD)" type="number" min="0" max="1000" step="0.01" value={settings.fee_per_trade} onChange={(event) => updateSetting("fee_per_trade", event.target.value)} required />
            <Field id="comparison-fee-bps" label="Commission (bps)" type="number" min="0" max="1000" step="0.01" value={settings.fee_bps} onChange={(event) => updateSetting("fee_bps", event.target.value)} required />
            <Field id="comparison-slippage" label="Slippage (bps)" type="number" min="0" max="1000" step="0.01" value={settings.slippage_bps} onChange={(event) => updateSetting("slippage_bps", event.target.value)} required />
          </fieldset>
          <div className="backtest-actions"><Button type="submit" disabled={loading}>{loading ? "Comparing…" : "Compare"}</Button><p className="muted text-xs">Completed daily history only. No real orders.</p></div>
          {loading && <p role="status">Running strategy comparison…</p>}
          {state.status === "error" && <p role="alert">{state.message}</p>}
          {state.status === "success" && <div className="comparison-status" role="status">
            <p>{state.data.results.filter((result) => result.status === "available").length < 2 ? "Insufficient data for a full comparison." : "Comparison complete."}</p>
            {state.data.results.map((result, index) => result.status === "unavailable" && <p key={index}>Strategy {index + 1} ({strategyNames[result.strategy.kind]}): {result.unavailable_reason}</p>)}
          </div>}
        </form>
      </Panel>
    </section>
  );
}

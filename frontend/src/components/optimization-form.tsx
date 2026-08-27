"use client";

import { useRef, useState, type FormEvent } from "react";
import { useBacktestOptimization } from "../hooks/use-backtest-optimization";
import type { OptimizationObjective, ParameterGrid } from "../lib/api";
import { Badge, Button, Field, Panel } from "./ui";

const latestCompletedDate = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

function parameterValues(value: string, integer: boolean): string[] {
  const values = value.split(",").map((item) => item.trim());
  if (!values.every((item) => (integer ? /^\d+$/ : /^\d+(?:\.\d{1,2})?$/).test(item)))
    throw new Error(`Enter comma-separated ${integer ? "whole numbers" : "numbers with at most two decimal places"}. Empty entries are not allowed.`);
  return values;
}

export function OptimizationForm() {
  const { state, load } = useBacktestOptimization();
  const [kind, setKind] = useState<ParameterGrid["kind"]>("sma_crossover");
  const [objective, setObjective] = useState<OptimizationObjective>("total_return_pct");
  const [settings, setSettings] = useState({ symbol: "", start: "", end: "", starting_cash: "10000.00", fee_per_trade: "0.00", fee_bps: "0", slippage_bps: "0", train_pct: "70" });
  const [ranges, setRanges] = useState({ fast: "10, 20", slow: "30, 50", periods: "7, 14", oversold: "25, 30", overbought: "70, 75" });
  const [error, setError] = useState("");
  const [edited, setEdited] = useState(false);
  const submitting = useRef(false);
  const loading = state.status === "loading";

  function updateSetting(key: keyof typeof settings, value: string): void {
    setSettings((current) => ({ ...current, [key]: value }));
  }
  function updateRange(key: keyof typeof ranges, value: string): void {
    setRanges((current) => ({ ...current, [key]: value }));
  }
  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setError("");
    setEdited(false);
    try {
      const grid: ParameterGrid = kind === "sma_crossover" ? {
        kind, fast_windows: parameterValues(ranges.fast, true).map(Number), slow_windows: parameterValues(ranges.slow, true).map(Number),
      } : { kind, periods: parameterValues(ranges.periods, true).map(Number), oversold: parameterValues(ranges.oversold, false), overbought: parameterValues(ranges.overbought, false) };
      const { train_pct, ...shared } = settings;
      await load({ ...shared, grid, objective, train_pct: Number(train_pct) });
    } catch (error) {
      setError(error instanceof Error ? error.message : "Optimization could not be run. Check the parameter values.");
    } finally {
      submitting.current = false;
    }
  }

  return <section id="optimization" className="optimization-section" aria-labelledby="optimization-title">
    <div className="section-heading"><div><span className="eyebrow">OPTIMIZE / CONFIGURE</span><h2 id="optimization-title">Strategy Optimization</h2></div><Badge>Paper simulation</Badge></div>
    <Panel className="backtest-panel">
      <form className="backtest-form" onSubmit={submit} onChange={() => { setEdited(true); setError(""); }} aria-busy={loading}>
        <p className="muted text-xs">Search parameters on the training period, then evaluate the selected strategy on later test data. Historical performance does not predict future returns.</p>
        <div className="backtest-fields">
          <Field id="optimization-symbol" label="Ticker" value={settings.symbol} onChange={(event) => updateSetting("symbol", event.target.value)} placeholder="AAPL" autoComplete="off" required disabled={loading} />
          <Field id="optimization-start" label="Start date" type="date" value={settings.start} onChange={(event) => updateSetting("start", event.target.value)} max={settings.end || latestCompletedDate} required disabled={loading} />
          <Field id="optimization-end" label="End date" type="date" value={settings.end} onChange={(event) => updateSetting("end", event.target.value)} min={settings.start || undefined} max={latestCompletedDate} required disabled={loading} />
          <Field id="optimization-capital" label="Starting capital (USD)" type="number" min="0.01" max="999999999999.99" step="0.01" value={settings.starting_cash} onChange={(event) => updateSetting("starting_cash", event.target.value)} required disabled={loading} />
        </div>
        <fieldset className="strategy-picker" disabled={loading}><legend>Strategy family</legend>
          {([ ["sma_crossover", "SMA"], ["rsi", "RSI"] ] as const).map(([value, label]) => <label key={value}><input type="radio" name="optimization-kind" value={value} checked={kind === value} onChange={() => setKind(value)} />{label}</label>)}
        </fieldset>
        <fieldset className="optimization-ranges" disabled={loading}><legend>Parameter values</legend>
          <p className="muted text-xs">Comma-separated values, up to 20 per parameter and 100 valid combinations. Invalid fast/slow or oversold/overbought pairs are skipped.</p>
          <div className="strategy-fields">{kind === "sma_crossover" ? <>
            <Field id="optimization-fast" label="Fast windows" value={ranges.fast} onChange={(event) => updateRange("fast", event.target.value)} required hint="Whole numbers, 2–250. Must be below a slow window." />
            <Field id="optimization-slow" label="Slow windows" value={ranges.slow} onChange={(event) => updateRange("slow", event.target.value)} required hint="Whole numbers, 3–500." />
          </> : <>
            <Field id="optimization-periods" label="RSI periods" value={ranges.periods} onChange={(event) => updateRange("periods", event.target.value)} required hint="Whole numbers, 2–100." />
            <Field id="optimization-oversold" label="Oversold levels" value={ranges.oversold} onChange={(event) => updateRange("oversold", event.target.value)} required hint="Greater than 0 and below 100; up to 2 decimals." />
            <Field id="optimization-overbought" label="Overbought levels" value={ranges.overbought} onChange={(event) => updateRange("overbought", event.target.value)} required hint="Above an oversold level and below 100; up to 2 decimals." />
          </>}</div>
        </fieldset>
        <fieldset className="strategy-picker" disabled={loading}><legend>Training objective · maximize</legend>
          {([ ["total_return_pct", "Return"], ["sharpe_ratio", "Sharpe ratio"], ["max_drawdown_pct", "Max drawdown (closest to zero)"] ] as const).map(([value, label]) => <label key={value}><input type="radio" name="optimization-objective" value={value} checked={objective === value} onChange={() => setObjective(value)} />{label}</label>)}
        </fieldset>
        <Field id="optimization-train" label="Training share (%)" type="number" min="50" max="90" step="1" value={settings.train_pct} onChange={(event) => updateSetting("train_pct", event.target.value)} required disabled={loading} hint="50–90% of trading days train; the remaining days test. The split is chronological." />
        <fieldset className="cost-fields" disabled={loading}><legend>Trading costs</legend>
          <Field id="optimization-fee" label="Fee per trade (USD)" type="number" min="0" max="1000" step="0.01" value={settings.fee_per_trade} onChange={(event) => updateSetting("fee_per_trade", event.target.value)} required />
          <Field id="optimization-fee-bps" label="Commission (bps)" type="number" min="0" max="1000" step="0.01" value={settings.fee_bps} onChange={(event) => updateSetting("fee_bps", event.target.value)} required />
          <Field id="optimization-slippage" label="Slippage (bps)" type="number" min="0" max="1000" step="0.01" value={settings.slippage_bps} onChange={(event) => updateSetting("slippage_bps", event.target.value)} required />
        </fieldset>
        <div className="backtest-actions"><Button type="submit" disabled={loading}>{loading ? "Optimizing…" : "Run Optimization"}</Button><p className="muted text-xs">Completed daily history only. No real orders.</p></div>
        {loading && <p role="status">Running parameter search and train/test evaluation…</p>}
        {(error || (!edited && state.status === "error")) && <p role="alert">{error || (state.status === "error" ? state.message : "")}</p>}
        {!edited && !error && state.status === "insufficient-data" && <p role="status">Insufficient data to select a strategy: {state.data.selection_reason}</p>}
        {!edited && !error && state.status === "success" && <p role="status">Optimization complete.</p>}
      </form>
    </Panel>
  </section>;
}

"use client";

import { useMemo, useState, type FormEvent } from "react";
import { runBacktest, type Backtest, type BacktestStrategy } from "../lib/api";
import { Badge, Button, Field, Panel } from "./ui";
import { BacktestResults, type BacktestResultState } from "./backtest-results";

type StrategyKind = BacktestStrategy["kind"];
const latestCompletedDate = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

export function BacktestForm() {
  const [symbol, setSymbol] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [startingCash, setStartingCash] = useState("10000.00");
  const [feePerTrade, setFeePerTrade] = useState("0.00");
  const [feeBps, setFeeBps] = useState("0");
  const [slippageBps, setSlippageBps] = useState("0");
  const [kind, setKind] = useState<StrategyKind>("buy_and_hold");
  const [fastWindow, setFastWindow] = useState("20");
  const [slowWindow, setSlowWindow] = useState("50");
  const [rsiPeriod, setRsiPeriod] = useState("14");
  const [oversold, setOversold] = useState("30");
  const [overbought, setOverbought] = useState("70");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Backtest | null>(null);
  const resultState = useMemo<BacktestResultState>(() => loading ? { status: "loading" } : error ? { status: "error", message: error } : result ? { status: "success", data: result } : { status: "idle" }, [loading, error, result]);
  const results = useMemo(() => <BacktestResults state={resultState} />, [resultState]);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    const strategy: BacktestStrategy = kind === "buy_and_hold" ? { kind }
      : kind === "sma_crossover" ? { kind, fast_window: Number(fastWindow), slow_window: Number(slowWindow) }
      : { kind, period: Number(rsiPeriod), oversold, overbought };
    try {
      setResult(await runBacktest({
        symbols: [symbol], start, end, starting_cash: startingCash, strategy,
        fee_per_trade: feePerTrade, fee_bps: feeBps, slippage_bps: slippageBps,
      }));
    } catch (error) {
      setError(error instanceof Error ? error.message : "Backtest could not be run. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section id="backtest" aria-labelledby="backtest-title">
      <div className="section-heading"><div><span className="eyebrow">02 / TEST</span><h2 id="backtest-title">Strategy backtest</h2></div><Badge>Paper simulation</Badge></div>
      <Panel className="backtest-panel">
        <form className="backtest-form" onSubmit={submit} aria-busy={loading}>
          <div className="backtest-fields">
            <Field id="backtest-symbol" label="Ticker" value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="AAPL" autoComplete="off" required disabled={loading} hint="One tradable ticker. Daily historical prices only." />
            <Field id="backtest-start" label="Start date" type="date" value={start} onChange={(event) => setStart(event.target.value)} max={end || undefined} required disabled={loading} />
            <Field id="backtest-end" label="End date" type="date" value={end} onChange={(event) => setEnd(event.target.value)} min={start || undefined} max={latestCompletedDate} required disabled={loading} />
            <Field id="backtest-capital" label="Starting capital (USD)" type="number" min="0.01" step="0.01" value={startingCash} onChange={(event) => setStartingCash(event.target.value)} required disabled={loading} />
          </div>

          <fieldset className="strategy-picker" disabled={loading}>
            <legend>Strategy</legend>
            {([ ["buy_and_hold", "Buy & Hold"], ["sma_crossover", "SMA Crossover"], ["rsi", "RSI"] ] as const).map(([value, label]) => (
              <label key={value}><input type="radio" name="strategy" value={value} checked={kind === value} onChange={() => setKind(value)} />{label}</label>
            ))}
          </fieldset>

          {kind === "sma_crossover" && <div className="strategy-fields" aria-label="SMA Crossover parameters">
            <Field id="backtest-fast-window" label="Fast window" type="number" min="2" max="250" step="1" value={fastWindow} onChange={(event) => setFastWindow(event.target.value)} required disabled={loading} />
            <Field id="backtest-slow-window" label="Slow window" type="number" min="3" max="500" step="1" value={slowWindow} onChange={(event) => setSlowWindow(event.target.value)} required disabled={loading} />
          </div>}
          {kind === "rsi" && <div className="strategy-fields" aria-label="RSI parameters">
            <Field id="backtest-rsi-period" label="RSI period" type="number" min="2" max="100" step="1" value={rsiPeriod} onChange={(event) => setRsiPeriod(event.target.value)} required disabled={loading} />
            <Field id="backtest-oversold" label="Oversold" type="number" min="0.01" max="99.99" step="0.01" value={oversold} onChange={(event) => setOversold(event.target.value)} required disabled={loading} />
            <Field id="backtest-overbought" label="Overbought" type="number" min="0.01" max="99.99" step="0.01" value={overbought} onChange={(event) => setOverbought(event.target.value)} required disabled={loading} />
          </div>}

          <fieldset className="cost-fields" disabled={loading}>
            <legend>Trading costs</legend>
            <Field id="backtest-fixed-fee" label="Fee per trade (USD)" type="number" min="0" max="1000" step="0.01" value={feePerTrade} onChange={(event) => setFeePerTrade(event.target.value)} required />
            <Field id="backtest-fee-bps" label="Commission (bps)" type="number" min="0" max="1000" step="0.01" value={feeBps} onChange={(event) => setFeeBps(event.target.value)} required />
            <Field id="backtest-slippage" label="Slippage (bps)" type="number" min="0" max="1000" step="0.01" value={slippageBps} onChange={(event) => setSlippageBps(event.target.value)} required />
          </fieldset>

          <div className="backtest-actions"><Button type="submit" disabled={loading}>{loading ? "Running backtest…" : "Run backtest"}</Button><p className="muted text-xs">Signals use completed daily bars. No orders leave this machine.</p></div>
        </form>
      </Panel>
      {results}
    </section>
  );
}

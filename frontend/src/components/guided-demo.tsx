"use client";

import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Badge, Button, Panel } from "./ui";

const steps = [
  { title: "Explore historical market charts", target: "market", action: "Open market workspace", text: "Choose a ticker and load daily history. Explore actual returned closes with the pointer or keyboard slider. Market prices come from Yahoo Finance; they are historical, not live quotes." },
  { title: "Inspect a paper portfolio", target: "activity", action: "Open paper portfolio", text: "Review virtual USD cash, holdings, transactions, allocation, and recorded equity. These are simulated balances, not real funds. If no portfolio exists, the view explains how to create one through the local API; this guide creates nothing." },
  { title: "Backtest a strategy", target: "backtest", action: "Open backtesting", text: "Choose Buy & Hold, SMA, or RSI, enter a ticker and completed historical period, then run a paper simulation. Inspect the returned metrics, equity, drawdown, and fills. Short periods may lack enough data to warm up indicators." },
  { title: "Understand optional AI Insights", target: "backtest", action: "Open backtesting & AI Insights", text: "After a successful backtest, find AI Insights below its results. Generate an explanation only if you choose to. Measured facts come from Vektor; AI interpretation can be wrong. The provider is optional, off by default, and paid when enabled. With AI off, facts remain available without a fabricated explanation." },
  { title: "Compare strategy configurations", target: "comparison", action: "Open strategy comparison", text: "Choose 2–5 distinct configurations using the same ticker, period, capital, and costs. Compare returned equity curves and metrics. Leader badges describe historical results, not recommendations; unavailable strategies stay explicitly unavailable." },
  { title: "Evaluate parameters out of sample", target: "optimization", action: "Open strategy optimization", text: "Configure an SMA or RSI parameter grid and chronological train/test split. Rankings use training data only; the selected parameters are then evaluated out of sample. Review the separate curves and overfitting flags. No flag is a promise of future performance." },
] as const;

export function GuidedDemo() {
  const [index, setIndex] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const entry = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (index !== null) heading.current?.focus(); }, [index]);
  const step = index === null ? null : steps[index];

  function exit(): void {
    setIndex(null);
    setNotice("");
    entry.current?.focus();
  }
  function visit(event: MouseEvent<HTMLAnchorElement>): void {
    if (!step || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = document.getElementById(step.target);
    if (!target) {
      event.preventDefault();
      setNotice("This section is unavailable here. You can continue the guide or skip it.");
      return;
    }
    target.tabIndex = -1;
    target.focus({ preventScroll: true });
  }

  return <section id="guided-demo" className="guided-demo" tabIndex={-1} aria-label="Optional Vektor guided demo" onKeyDown={(event) => { if (event.key === "Escape" && step) { event.stopPropagation(); exit(); } }}>
    <div className="demo-entry"><div><span className="eyebrow">START WITH A GUIDED TOUR</span><p className="demo-entry-title">Your first research session</p><p className="muted text-xs">Six steps. Your own exploration. No sample balances, automatic trades, or AI calls.</p></div>
      <Button ref={entry} type="button" variant="primary" aria-expanded={step !== null} aria-controls={step ? "demo-steps" : undefined} onClick={() => { setNotice(""); if (index === 0) heading.current?.focus(); else setIndex(0); }}>{step ? "Restart demo" : "Explore Demo"}</Button>
    </div>
    {step && index !== null && <Panel id="demo-steps" className="demo-panel" aria-labelledby="demo-step-title">
      <div className="panel-heading"><Badge>Step {index + 1} of {steps.length}</Badge><Button type="button" variant="ghost" onClick={exit}>Skip demo</Button></div>
      <h2 id="demo-step-title" ref={heading} tabIndex={-1}>{step.title}</h2>
      <p>{step.text}</p>
      <a className="button button-primary" href={`#${step.target}`} onClick={visit}>{step.action}</a>
      <p className="demo-availability muted text-xs">You can continue without a backend or AI provider. Features show their actual loading, empty, or error states. <a className="demo-text-link" href="#backend-status">Check backend status</a>.</p>
      <p className="muted text-xs">Return through <strong>Demo guide</strong> in the top bar. Use Skip or Escape inside the guide to exit without changing your research.</p>
      {notice && <p role="status">{notice}</p>}
      <div className="demo-controls"><Button type="button" variant="secondary" disabled={index === 0} onClick={() => { setNotice(""); setIndex(index - 1); }}>Back</Button>
        {index === steps.length - 1 ? <Button type="button" onClick={exit}>Finish demo</Button> : <Button type="button" onClick={() => { setNotice(""); setIndex(index + 1); }}>Next</Button>}
      </div>
    </Panel>}
  </section>;
}

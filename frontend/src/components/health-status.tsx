"use client";

import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "../lib/api";
import { Badge, Button } from "./ui";

type ConnectionState =
  | { status: "loading" }
  | { status: "connected"; health: HealthResponse; checkedAt: Date }
  | { status: "error"; message: string };

export function HealthStatus() {
  const [state, setState] = useState<ConnectionState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function checkHealth(): Promise<void> {
      try {
        const health = await getHealth(controller.signal);
        if (!controller.signal.aborted) setState({ status: "connected", health, checkedAt: new Date() });
      } catch (error) {
        if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "Backend health check failed. Try again." });
      }
    }
    void checkHealth();
    return () => controller.abort();
  }, [attempt]);

  return (
    <section id="backend-status" className={`health-status health-${state.status}`} aria-labelledby="backend-status-title" aria-busy={state.status === "loading"}>
      <div className="health-summary" role="status" aria-live="polite" aria-atomic="true">
        <div className="health-heading"><h2 id="backend-status-title">Backend connection</h2><Badge tone={state.status === "connected" ? "positive" : state.status === "error" ? "warning" : "neutral"}>{state.status === "loading" ? "Checking…" : state.status === "connected" ? "Connected" : "Connection error"}</Badge></div>
        {state.status === "loading" && <p>Checking the paper-only health endpoint. Market data remains unavailable.</p>}
        {state.status === "error" && <p>{state.message}</p>}
        {state.status === "connected" && <p>{state.health.app} · {state.health.version} · {state.health.environment} · Last check passed at <time dateTime={state.checkedAt.toISOString()}>{state.checkedAt.toLocaleTimeString()}</time>. Health only; no market feed.</p>}
      </div>
      <Button variant="secondary" disabled={state.status === "loading"} aria-label="Check backend connection" onClick={() => { setState({ status: "loading" }); setAttempt((value) => value + 1); }}>{state.status === "loading" ? "Checking…" : state.status === "error" ? "Retry connection" : "Check again"}</Button>
    </section>
  );
}

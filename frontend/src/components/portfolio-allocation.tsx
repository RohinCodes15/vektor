"use client";

import { useEffect, useState } from "react";
import { getPortfolioAllocation, getPortfolioRisk, type PortfolioAllocation, type PortfolioRisk } from "../lib/api";
import { AllocationSummary } from "./allocation-summary";
import { PortfolioRiskView } from "./portfolio-risk";
import { Badge, Button, Panel } from "./ui";

type Resource<T> = { key: string } & ({ status: "success"; data: T } | { status: "error"; message: string });

export function PortfolioAllocationSection({ id, refreshVersion = 0 }: { id: string; refreshVersion?: number }) {
  const [allocation, setAllocation] = useState<Resource<PortfolioAllocation> | null>(null);
  const [risk, setRisk] = useState<Resource<PortfolioRisk> | null>(null);
  const [attempt, setAttempt] = useState(0);
  const key = `${id}:${refreshVersion}:${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    function receive<T>(request: Promise<T>, setter: (value: Resource<T>) => void): void {
      void request.then((data) => {
        if (!controller.signal.aborted) setter({ key, status: "success", data });
      }).catch((error: unknown) => {
        if (!controller.signal.aborted) setter({ key, status: "error", message: error instanceof Error ? error.message : "Portfolio data unavailable." });
      });
    }
    void Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      receive(getPortfolioAllocation(id, controller.signal), setAllocation);
      receive(getPortfolioRisk(id, controller.signal), setRisk);
    });
    return () => controller.abort();
  }, [id, key]);
  const currentAllocation = allocation?.key === key ? allocation : null;
  const currentRisk = risk?.key === key ? risk : null;
  return <section className="portfolio-allocation" aria-labelledby="allocation-section-title">
    <div className="section-heading"><div><span className="eyebrow">EXPOSURE / CURRENT HOLDINGS</span><h2 id="allocation-section-title">Allocation & risk</h2></div><Badge>Paper portfolio</Badge></div>
    <div className="allocation-toolbar"><p className="muted text-xs">Current portfolio exposure, separate from recorded performance.</p><Button variant="secondary" disabled={!currentAllocation || !currentRisk} onClick={() => setAttempt((value) => value + 1)}>Refresh allocation & risk</Button></div>
    <div aria-busy={!currentAllocation}>{!currentAllocation ? <Panel className="chart-state"><p role="status">Loading portfolio allocation…</p></Panel> : currentAllocation.status === "error" ? <Panel className="chart-state"><h3>Allocation unavailable</h3><p role="alert">{currentAllocation.message}</p><Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Retry allocation</Button></Panel> : <AllocationSummary key={key} allocation={currentAllocation.data} />}</div>
    <div aria-busy={!currentRisk}>{!currentRisk ? <Panel className="chart-state"><p role="status">Loading portfolio risk…</p></Panel> : currentRisk.status === "error" ? <Panel className="chart-state"><h3>Risk request failed</h3><p role="alert">{currentRisk.message}</p><Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>Retry risk</Button></Panel> : <PortfolioRiskView key={key} risk={currentRisk.data} />}</div>
  </section>;
}

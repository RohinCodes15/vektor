import { DashboardShell } from "@/components/dashboard-shell";
import { MarketWorkspace } from "@/components/market-workspace";
import { Reveal } from "@/components/reveal";
import { Badge, Button, MetricCard, Panel } from "@/components/ui";

export default function Home() {
  return (
    <DashboardShell>
      <Reveal>
        <section id="overview" aria-labelledby="overview-title">
          <div className="dashboard-intro">
            <div><div className="eyebrow"><span className="status-dot" /> YOUR RESEARCH DESK</div><h1 id="overview-title">A clearer view.<br className="mobile-break" /> A measured approach.</h1><p className="lead">Test ideas. Study the outcome. Keep your capital out of it.</p></div>
            <Button disabled>New simulation · Coming soon</Button>
          </div>
          <div className="data-notice"><span className="notice-symbol" aria-hidden="true">i</span><p><strong>Workspace preview</strong><span>Portfolio and market data are not connected. All values remain unavailable until a data source is implemented.</span></p><Badge>NO LIVE DATA</Badge></div>
          <div className="section-heading"><div><span className="eyebrow">01 / YOUR CAPITAL, SIMULATED</span><h2>Portfolio overview</h2></div><span className="mono muted text-xs">BASE CURRENCY / USD</span></div>
          <div className="metrics-grid">
            <MetricCard label="Portfolio value" value="—" detail="No simulation loaded" />
            <MetricCard label="Total return" value="—" detail="Awaiting simulation results" />
            <MetricCard label="Available cash" value="—" detail="No paper balance configured" />
            <MetricCard label="Open positions" value="—" detail="Position data unavailable" />
          </div>
          <div className="portfolio-grid">
            <Panel className="performance-panel" aria-labelledby="performance-title">
              <div className="panel-heading"><div><h3 id="performance-title">Portfolio performance</h3><p className="muted text-xs">The bigger picture, one decision at a time.</p></div><Badge>Awaiting results</Badge></div>
              <div className="performance-empty"><div className="empty-axis" aria-hidden="true"><span /><span /><span /><span /></div><div className="empty-copy"><span className="empty-icon" aria-hidden="true">↗</span><h3>Your first chapter is unwritten.</h3><p>Run a paper simulation to see your equity curve here.<br />No performance history has been generated.</p><a href="#market" className="text-link">Explore the market workspace <span aria-hidden="true">→</span></a></div></div>
              <div className="chart-footer"><span className="mono">EQUITY / USD</span><span>No synthetic returns. No live prices.</span></div>
            </Panel>
            <Panel className="session-panel" aria-labelledby="session-title">
              <div className="panel-heading"><h3 id="session-title">Research session</h3><span className="mono muted text-xs">01</span></div>
              <div className="session-emblem" aria-hidden="true">∨</div><h3>Built for independent thinking.</h3><p className="muted text-sm">A focused workspace on your machine. Every strategy stays in simulation.</p>
              <dl className="session-facts"><div><dt>Execution</dt><dd className="text-teal">Paper only</dd></div><div><dt>Market feed</dt><dd>Not connected</dd></div><div><dt>Simulation tools</dt><dd>Coming soon</dd></div></dl>
            </Panel>
          </div>
        </section>
        <MarketWorkspace />
        <section id="activity" aria-labelledby="activity-title">
          <div className="section-heading"><div><span className="eyebrow">03 / THE RESEARCH LOG</span><h2 id="activity-title">Recent activity</h2></div><Badge>Paper workspace</Badge></div>
          <Panel className="activity-panel"><span className="activity-mark" aria-hidden="true">↳</span><div><h3>A clean slate.</h3><p className="muted text-sm">Simulation activity will appear here. Nothing has been executed.</p></div><Button variant="secondary" disabled>View history · Coming soon</Button></Panel>
        </section>
      </Reveal>
    </DashboardShell>
  );
}

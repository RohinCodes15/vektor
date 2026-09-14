import { DashboardShell } from "@/components/dashboard-shell";
import { MarketWorkspace } from "@/components/market-workspace";
import { Reveal } from "@/components/reveal";
import { PortfolioDashboard } from "@/components/portfolio-dashboard";
import { Badge, Button, Panel } from "@/components/ui";

export default function Home() {
  return (
    <DashboardShell>
      <Reveal>
        <section id="overview" aria-labelledby="overview-title">
          <div className="dashboard-intro">
            <div><div className="eyebrow"><span className="status-dot" /> YOUR RESEARCH DESK</div><h1 id="overview-title">A clearer view.<br className="mobile-break" /> A measured approach.</h1><p className="lead">Test ideas. Study the outcome. Keep your capital out of it.</p></div>
            <Button disabled>New simulation · Coming soon</Button>
          </div>
          <div className="data-notice"><span className="notice-symbol" aria-hidden="true">i</span><p><strong>Paper portfolio workspace</strong><span>Virtual balances valued at completed daily closes. No live quotes or real-money execution.</span></p><Badge>NO LIVE DATA</Badge></div>
          <PortfolioDashboard />
          <div className="portfolio-grid">
            <Panel className="session-panel" aria-labelledby="session-title">
              <div className="panel-heading"><h3 id="session-title">Research session</h3><span className="mono muted text-xs">01</span></div>
              <div className="session-emblem" aria-hidden="true">∨</div><h3>Built for independent thinking.</h3><p className="muted text-sm">A focused workspace on your machine. Every strategy stays in simulation.</p>
              <dl className="session-facts"><div><dt>Execution</dt><dd className="text-teal">Paper only</dd></div><div><dt>Live quote feed</dt><dd>Not connected</dd></div><div><dt>Simulation tools</dt><dd>Coming soon</dd></div></dl>
            </Panel>
          </div>
        </section>
        <MarketWorkspace />

      </Reveal>
    </DashboardShell>
  );
}

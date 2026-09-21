import { Badge, Button, Field, Panel } from "@/components/ui";
import { Reveal } from "@/components/reveal";

const principles = [
  ["01", "Research with intent", "Define a hypothesis before running a strategy. Keep the process repeatable."],
  ["02", "Keep it on your machine", "A local-first workspace. No account, credentials, or paid services required."],
  ["03", "Stay in simulation", "Every trade is paper-only. Explore ideas without putting capital at risk."],
] as const;

export default function Home() {
  return <div className="app-shell">
    <aside className="sidebar" aria-label="Workspace navigation">
      <a className="brand" href="#overview" aria-label="Vektor home"><span className="brand-mark" aria-hidden="true">∨</span>vektor<span className="brand-period">.</span></a>
      <div className="workspace-label">LOCAL WORKSPACE <span className="status-dot" /></div>
      <nav aria-label="Main"><a href="#overview" className="nav-link nav-active">Overview <span>01</span></a><a href="#principles" className="nav-link">Principles <span>02</span></a><a href="#components" className="nav-link">Design system <span>03</span></a></nav>
      <div className="sidebar-note"><Badge tone="positive">Paper only</Badge><p>Your ideas. Your machine.<br />No real-money execution.</p><span className="mono">VEKTOR / 0.1</span></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div><span className="muted">Workspace</span><span className="breadcrumb">/</span>Overview</div><span className="mono muted text-xs">LOCAL-FIRST <span className="text-teal">↗</span></span></header>
      <main id="main"><Reveal>
        <section id="overview" aria-labelledby="overview-title" className="intro">
          <div className="eyebrow"><span className="status-dot" /> THE RESEARCH WORKSPACE</div>
          <div className="intro-row"><div><h1 id="overview-title">Precision starts<br />with a hypothesis.</h1><p className="lead">A focused environment for algorithmic research.<br className="desktop-break" /> Build conviction through paper trading.</p></div><a className="button button-secondary" href="#components">Explore the system <span aria-hidden="true">↗</span></a></div>
        </section>
        <div className="section-heading"><h2>Workspace overview</h2><Badge>Foundation release</Badge></div>
        <div className="overview-grid">
          <Panel className="research-panel" aria-labelledby="research-title"><div className="panel-heading"><span className="eyebrow">RESEARCH ENVIRONMENT</span><Badge tone="positive">Paper mode</Badge></div><div className="research-visual" aria-hidden="true"><svg viewBox="0 0 600 150" preserveAspectRatio="none"><path d="M0 125 L45 120 L70 130 L110 99 L145 106 L180 80 L215 90 L250 55 L285 70 L320 48 L360 58 L395 25 L430 42 L465 22 L505 30 L550 8 L600 18" /></svg><span className="chart-label">HYPOTHESIS → OBSERVATION → ITERATION</span></div><h3 id="research-title">Room to test your thinking.</h3><p className="muted">A deliberate starting point for your next strategy.<br />Simulation tools will live here as they become available.</p><div className="panel-footer"><span className="mono text-xs muted">ILLUSTRATIVE RESEARCH PATH · NO MARKET DATA</span></div></Panel>
          <Panel className="status-panel" aria-labelledby="status-title"><div className="panel-heading"><h3 id="status-title">System boundaries</h3><span className="muted" aria-hidden="true">⌁</span></div><dl className="status-list"><div><dt>Execution</dt><dd><Badge tone="positive">Paper only</Badge></dd></div><div><dt>Environment</dt><dd>Local machine</dd></div><div><dt>Account required</dt><dd>No</dd></div><div><dt>Simulation API</dt><dd><Badge tone="warning">Not available</Badge></dd></div></dl><div className="notice"><span aria-hidden="true">↳</span><p>No brokerage connection.<br /><span className="muted">Real-money execution is excluded.</span></p></div></Panel>
        </div>
        <section id="principles" aria-labelledby="principles-title"><div className="section-heading"><h2 id="principles-title">Built on clear principles</h2><span className="mono muted text-xs">LESS NOISE. MORE SIGNAL.</span></div><div className="principles-grid">{principles.map(([number, title, description]) => <Panel key={number}><span className="mono principle-number">{number} /</span><h3>{title}</h3><p className="muted">{description}</p></Panel>)}</div></section>
        <section id="components" aria-labelledby="components-title"><div className="section-heading"><div><h2 id="components-title">The working palette</h2><p className="muted text-sm">Shared primitives, designed for focus.</p></div><Badge>Component reference</Badge></div><Panel className="component-panel"><div><h3>Actions & states</h3><p className="muted text-sm">Clear hierarchy. Restrained emphasis.</p><div className="component-row"><a href="#overview" className="button button-primary">Back to overview <span aria-hidden="true">↑</span></a><Button variant="secondary" disabled>Run simulation</Button></div><p className="muted text-xs">Simulation actions are unavailable in this foundation release.</p><div className="component-row"><Badge tone="positive">Paper</Badge><Badge>Draft</Badge><Badge tone="warning">Pending</Badge></div></div><div><h3>Inputs</h3><div className="mt-5"><Field id="strategy-name" label="Strategy name" placeholder="e.g. Mean reversion" hint="Component preview only. This value is not saved." maxLength={100} autoComplete="off" /></div></div><div><h3>Surfaces & accent</h3><div className="swatches"><div><span className="swatch swatch-canvas" />Canvas</div><div><span className="swatch swatch-panel" />Surface</div><div><span className="swatch swatch-teal" />Accent</div></div><p className="mono muted text-xs">CHARCOAL / TEAL / CLARITY</p></div></Panel></section>
        <footer className="page-footer"><span>Vektor <span className="muted">/ Independent thinking, measured.</span></span><span className="mono text-xs muted">LOCAL-FIRST · PAPER-ONLY</span></footer>
      </Reveal></main>
    </div>
  </div>;
}

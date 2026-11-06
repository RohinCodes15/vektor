"use client";

import { useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { Badge } from "./ui";

const sections = [
  { id: "overview", label: "Overview", icon: "◫" },
  { id: "market", label: "Market workspace", icon: "⌁" },
  { id: "activity", label: "Activity", icon: "↳" },
] as const;

function subscribeToHash(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobileToggle = useRef<HTMLButtonElement>(null);
  const hash = useSyncExternalStore(subscribeToHash, () => window.location.hash || "#overview", () => "#overview");

  function closeMobileNavigation(): void {
    setMobileOpen(false);
    mobileToggle.current?.focus();
  }

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "mobile-nav-open" : ""}`}>
      <aside className="sidebar" aria-label="Workspace navigation" onKeyDown={(event) => {
        if (event.key === "Escape" && mobileOpen) closeMobileNavigation();
      }}>
        <div className="sidebar-header">
          <a className="brand" href="#overview" aria-label="Vektor home">
            <span className="brand-mark" aria-hidden="true">∨</span><span className="brand-name">vektor<span className="brand-period">.</span></span>
          </a>
          <button ref={mobileToggle} className="icon-button mobile-toggle" type="button" aria-label={mobileOpen ? "Close navigation" : "Open navigation"} aria-expanded={mobileOpen} aria-controls="sidebar-navigation" onClick={() => setMobileOpen(!mobileOpen)}>
            <span aria-hidden="true">{mobileOpen ? "×" : "☰"}</span>
          </button>
        </div>
        <div id="sidebar-navigation" className="sidebar-content">
          <div className="workspace-label"><span className="sidebar-copy">WORKSPACE / 01</span><span className="status-dot" /></div>
          <nav aria-label="Main">
            {sections.map(({ id, label, icon }) => (
              <a key={id} href={`#${id}`} className={`nav-link ${hash === `#${id}` ? "nav-active" : ""}`} aria-label={label} aria-current={hash === `#${id}` ? "location" : undefined} title={collapsed ? label : undefined} onClick={() => { if (mobileOpen) closeMobileNavigation(); }}>
                <span className="nav-icon" aria-hidden="true">{icon}</span><span className="sidebar-copy">{label}</span>
              </a>
            ))}
          </nav>
          <div className="sidebar-divider" />
          <span className="sidebar-caption sidebar-copy">RESEARCH TOOLS</span>
          <button type="button" className="nav-link future-link" disabled aria-label="Strategies — coming soon"><span className="nav-icon" aria-hidden="true">⧉</span><span className="sidebar-copy">Strategies <small>Soon</small></span></button>
          <button type="button" className="nav-link future-link" disabled aria-label="Backtests — coming soon"><span className="nav-icon" aria-hidden="true">⏱</span><span className="sidebar-copy">Backtests <small>Soon</small></span></button>
          <div className="sidebar-note"><span className="local-mark" aria-hidden="true">⌘</span><div className="sidebar-copy"><strong>On your machine.</strong><p>No account. No brokerage.<br />Your research stays local.</p></div></div>
        </div>
        <button type="button" className="collapse-toggle" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} aria-controls="sidebar-navigation" onClick={() => setCollapsed(!collapsed)} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          <span aria-hidden="true">{collapsed ? "→" : "←"}</span><span className="sidebar-copy">Collapse sidebar</span>
        </button>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <nav aria-label="Breadcrumb"><span className="muted">Workspace</span><span className="breadcrumb" aria-hidden="true">/</span><a href="#overview">Dashboard</a></nav>
          <div className="topbar-actions"><span className="local-status"><span className="status-dot" />Local workspace</span><Badge tone="positive">PAPER ONLY</Badge><a className="icon-button help-link" href="#workspace-notes" aria-label="About this workspace">?</a></div>
        </header>
        <main id="main">{children}</main>
        <footer className="shell-footer" id="workspace-notes"><span>Vektor <span className="muted">/ Research with intent.</span></span><span className="muted">Local-first. Paper trading only. No real-money execution.</span></footer>
      </div>
    </div>
  );
}

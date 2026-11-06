# Vektor frontend

Local-first, paper-only workspace foundation. Next.js App Router, TypeScript, Tailwind CSS v4, and Motion. No accounts, remote fonts, analytics, or backend connection required.

```sh
npm ci
npm run dev       # http://localhost:3000
npm run lint
npm run typecheck
npm run build
npm test         # tests the production build
npm start         # serve the production build
```

Use Node.js 22.13+ and npm. Dependencies are pinned in package-lock.json.

## Design system

`src/app/globals.css` owns Tailwind theme tokens, charcoal surfaces, teal accent, typography, spacing, visible keyboard focus, responsive layouts, and reduced-motion styles. System fonts work offline. `src/components/ui.tsx` provides typed Button (three variants), Badge (three tones), Panel, and labeled Field primitives; they forward native attributes. Pass `aria-invalid` and an explanatory hint for invalid fields.

## Phase 1C dashboard

`src/components/dashboard-shell.tsx` owns the responsive shell: desktop collapse/expand, a mobile disclosure menu with Escape support, native anchor navigation, hash-aware active links, and the persistent PAPER ONLY indicator. The mobile menu expands in document flow, so it does not need a modal focus trap. Sidebar state is intentionally session-only; nothing is saved to local storage.

`MetricCard` in `src/components/ui.tsx` composes the existing Panel primitive. Portfolio metrics show unavailable values, not fabricated balances or zero positions. The performance view is an empty state, not a synthetic chart.

`src/components/market-workspace.tsx` provides case-insensitive symbol/company search, a no-results state, and selectable reference instruments. Static symbol metadata is explicitly a reference list; there are no prices, timestamps, returns, market-open claims, or network requests. Selection updates the instrument details. Simulation, paper orders, backtests, strategies, and history are disabled and marked coming soon. No shared API contracts were changed.

`src/components/reveal.tsx` retains the Motion entrance and OS reduced-motion support. UI colors, typography, native focus states, and reduced-motion CSS follow the existing design system. No new dependencies were added.

Tests exercise the production-rendered shell, paper-only and data-unavailable boundaries, anchor targets, labeled search, initial disclosure states, and color contrast. Browser checks cover desktop collapse/expand, mobile open/close and Escape, symbol selection, filtering and no-results recovery, active navigation, and desktop/mobile overflow. Assistive-technology testing remains manual.

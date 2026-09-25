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

`src/components/market-workspace.tsx` provides case-insensitive symbol/company search, a no-results state, and selectable reference instruments. Static symbol metadata is explicitly a reference list with no live quotes. Selection updates the instrument details; StockHistory requests historical prices separately on demand. Simulation, paper orders, backtests, strategies, and history are disabled and marked coming soon. No shared API contracts were changed.

`src/components/reveal.tsx` retains the Motion entrance and OS reduced-motion support. UI colors, typography, native focus states, and reduced-motion CSS follow the existing design system. No new dependencies were added.

Tests exercise the production-rendered shell, paper-only and data-unavailable boundaries, anchor targets, labeled search, initial disclosure states, and color contrast. Browser checks cover desktop collapse/expand, mobile open/close and Escape, symbol selection, filtering and no-results recovery, active navigation, and desktop/mobile overflow. Assistive-technology testing remains manual.

## Phase 1D: connection and motion

The dashboard checks `GET /api/v1/health` on mount and when **Retry connection / Check again** is pressed. The connected state describes the last successful check and shows its time; it is a snapshot, not continuous monitoring. Health success never unlocks market data or simulation controls. No polling or additional dependencies were added.

The default backend origin is `http://localhost:8000`. Optionally copy `.env.example` to `.env.local` in `frontend/` and set `NEXT_PUBLIC_API_ORIGIN` to an HTTP(S) origin without a path or credentials. This is public configuration, not a secret. Restart development or rebuild production after changing it. Run the existing backend per `../backend/README.md`. Its CORS settings already allow `http://localhost:3000`; other frontend origins require coordination with the backend owner.

`src/lib/api.ts` mirrors HealthResponse and validates all five fields, including literal `ok` and `paper`, with no extra fields. Requests omit credentials, bypass caches, reject redirects, time out after five seconds (including body reading), and support cancellation. HTTP errors, unreachable/CORS failures, invalid JSON, and incompatible responses produce safe messages; raw server response bodies are never displayed. The shell remains usable when the backend is unavailable.

Motion is limited to short 2–4px entrances, once-per-view cards, navigation hover, and instrument selection. A shared MotionConfig respects the OS reduced-motion preference, with zero duration and CSS transform/transition overrides as a backstop. Content is visible in server HTML, with no loading fade, loop, or animation-delayed status changes. Connection feedback is a polite live region, instrument changes are announced, and the skip link has a focusable main target.

API tests use the native Node TypeScript stripping flag and mocked fetch to cover the exact endpoint/options, configured and invalid origins, strict paper-only validation, HTTP/JSON/network failures, timeout, and cancellation. Rendered-page and contrast tests remain in place.

## Market history client

`getMarketHistory({ symbol, start, end }, signal?)` in `src/lib/api.ts` requests read-only `GET /api/v1/market/history`, using the existing origin, no-cache/no-credentials transport, five-second timeout, and cancellation. Dates are inclusive `YYYY-MM-DD` calendar dates; interval is always `1d`. Symbols are trimmed/uppercased according to the backend contract. Errors distinguish invalid input, no data (404), rejected queries (422), invalid provider data (502), unavailable providers (503), network failures, and malformed/incompatible responses. Raw error bodies are not displayed.

Response validation checks exact fields, matching query metadata, timezone-aware fetch time, source/cache metadata, finite positive OHLC/adjusted prices, OHLC bounds, safe integer volume, and strictly increasing dates inside the requested range. It accepts empty bar arrays and nullable currency, preserves provider values, and never fills or repairs data. Volumes outside JavaScript's safe integer range are rejected to prevent silent rounding.

`useMarketHistory()` exposes `{ state, load }` for future consumers. `state.status` is `idle`, `loading`, `success` (with typed `data`), or `error` (with `message`). Call `load(query)` from a user action; it clears stale data, cancels the previous request, ignores superseded results, and cancels on unmount. StockHistory consumes this hook in the market workspace; it never fetches or substitutes live quotes.

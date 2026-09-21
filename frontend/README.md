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

`src/components/reveal.tsx` is the small Motion client boundary. It respects the OS reduced-motion preference. The rest of the page is server rendered. Navigation uses native section anchors; all content remains readable without JavaScript.

The home page doubles as a workspace foundation and component reference. Its chart is decorative and explicitly illustrative; no prices, returns, account balances, API health, or simulation results are claimed. The input is a labeled, unsaved component preview. Run simulation is disabled because simulation endpoints do not exist. No shared API contracts were changed.

Tests check the rendered page's paper-only boundaries, anchor targets, labels, and component semantics. Desktop (1440px) and mobile (375px) layouts were checked in-browser; assistive-technology testing remains manual.

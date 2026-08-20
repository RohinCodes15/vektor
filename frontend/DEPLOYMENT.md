# Frontend deployment (Phase 5B)

Use Vercel's Next.js hosting with the single-machine Fly.io backend described in
[`backend/DEPLOYMENT.md`](../backend/DEPLOYMENT.md). Vercel Hobby is free for eligible personal,
non-commercial use; check current plan terms before publishing. No deployment or resource creation is automatic.
The frontend works locally without hosting accounts; all execution remains paper-only.

## Configuration

The only required public production variable is `NEXT_PUBLIC_API_ORIGIN`: the backend's exact HTTPS
origin, for example `https://your-vektor-backend.fly.dev`. No `/api/v1` suffix, path, credentials,
query, or fragment. Missing values, HTTP, and loopback hosts fail the production build.
Next.js embeds this value into the browser bundle **at build time**; changing it requires a rebuild.
Do not use `next.config`'s `env` option to copy backend variables into browser code.

Never add backend settings, database paths, `VEKTOR_AI_API_KEY`, `ANTHROPIC_API_KEY`, or other secrets
to the frontend host or any `NEXT_PUBLIC_*` variable. AI remains optional and configured on the backend only.

Development keeps its `http://localhost:8000` default. To override it, copy `.env.example` to
`.env.local` (uncommitted), set the origin, and restart `npm run dev`.

## Vercel project settings

- Import the existing repository; set **Root Directory** to `frontend` and framework to **Next.js**.
- Select Node.js **22.x** (at least 22.13); use the committed npm lockfile and `npm ci`.
- Build command: `npm run build`. Keep the default Next.js output setting; this app is not a static export.
- Set `NEXT_PUBLIC_API_ORIGIN` for Production before building. Set Preview separately only if its
  frontend origin is allowed by the intended backend. Avoid sending previews to a shared production backend by accident.
- The backend owner must configure `VEKTOR_CORS_ORIGINS` with the exact frontend HTTPS origin(s),
  as Phase 5A documents. CORS is not authentication. Do not use a wildcard or expose an untrusted demo's
  paper portfolios or optional paid AI endpoint to arbitrary visitors.

No Vercel manifest, proxy, frontend database, or extra dependencies are needed. The existing browser
client calls the Fly.io backend directly using versioned `/api/v1` endpoints, without credentials or caching.

## Verify before publishing

```sh
npm ci
export NEXT_PUBLIC_API_ORIGIN=https://your-vektor-backend.fly.dev
npm run typecheck
npm run lint
npm run build
npm test
npm start
```

The build renders the shell without contacting the backend. Health, portfolios, and research requests
run in the browser. Existing timeouts, retry actions, cancellation, safe API errors, and the AI
`unavailable` state remain intact; no data is invented during downtime. Fly auto-start can make an initial
health request time out; retry after the machine starts. Provider availability is separate from health.

On the deployed frontend, verify the browser requests your configured backend (never the visitor's
localhost), CORS permits it, and health reports `trading_mode: "paper"`. Check portfolio reads,
backtesting, comparison, optimization, and AI-off behavior. Keep backend secrets on Fly.io.
Do not publish until the backend URL, frontend origin, persistence, and backend access controls are reviewed.
Roll back to a prior frontend deployment built against the correct backend; a frontend rollback does not alter SQLite data.

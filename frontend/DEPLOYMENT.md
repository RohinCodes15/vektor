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

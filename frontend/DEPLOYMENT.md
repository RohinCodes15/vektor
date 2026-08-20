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

# Vektor frontend

A local-first, paper-only research dashboard built with Next.js App Router, React, TypeScript, Tailwind CSS v4, and Motion. It displays real historical market data and simulated portfolio/backtest results; it never routes orders to a broker.

The shell and optional guided demo render without a backend. Health checks and all portfolio, market-history, backtest, comparison, optimization, and AI-analysis requests require the FastAPI backend. Market data additionally depends on Yahoo Finance availability. An unavailable backend produces connection/error states, never sample financial data.

## Local setup

Use Node.js **22.13+** and npm. Dependencies are pinned in `package-lock.json`.

Start the backend in a separate terminal using [its setup instructions](../backend/README.md): from `backend/`, run `uv sync`, then `uv run uvicorn app.main:app --reload`. Its default origin is `http://localhost:8000`.

From this directory:

```sh
npm ci
# Optional: development already defaults to http://localhost:8000.
cp .env.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The backend's development CORS defaults permit this origin. If either origin changes, configure the backend's exact allowed frontend origin; a frontend variable alone cannot change CORS. Configuration files such as `.env.local` are ignored by Git.

## Public environment configuration

`NEXT_PUBLIC_API_ORIGIN` is the backend **origin only**: no `/api/v1` suffix, path, query, fragment, or credentials. The API client adds the versioned endpoint path.

- **Development:** optional; defaults to `http://localhost:8000`. HTTP or HTTPS origins are accepted.
- **Production:** required before building; use the actual HTTPS backend origin. `next.config.ts` and `src/lib/api-origin.ts` reject missing, HTTP, loopback, or malformed production origins. The client also validates the origin before requests.
- **Build time:** Next.js embeds `NEXT_PUBLIC_API_ORIGIN` in browser JavaScript. Restart development or rebuild production after changing it; changing only a running server's environment does not update an existing browser bundle.
- **Secrets:** this variable is public. Never add backend credentials, `VEKTOR_AI_API_KEY`, `ANTHROPIC_API_KEY`, or other secrets to this frontend or any `NEXT_PUBLIC_*` variable.

AI analysis is optional and configured on the backend only. With the provider off, measured facts remain available while AI interpretation is explicitly unavailable. Enabling Anthropic incurs provider charges. The guide does not generate AI requests automatically.

## Verification and production

```sh
npm run typecheck
npm run lint
# Reserved example for build verification only; replace with your real backend before publishing.
NEXT_PUBLIC_API_ORIGIN=https://backend.example.com npm run build
npm test
npm start
```

Build before `npm test`: rendered-page tests read `.next/server/app/index.html`. For restricted environments where Turbopack cannot bind its build-worker port, the supported alternative is `npm run build -- --webpack` with the same environment variable. Neither build command requires a reachable backend; runtime features do.

See [frontend deployment](DEPLOYMENT.md) and [backend deployment](../backend/DEPLOYMENT.md) for Vercel/Fly.io settings, exact HTTPS CORS origins, persistent storage, costs, and access limitations. No deployment is performed by these commands. The API has no authentication; do not expose it to untrusted users merely because CORS is configured.


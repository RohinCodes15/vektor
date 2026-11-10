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


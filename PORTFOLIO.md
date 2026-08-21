# Vektor — Technical Portfolio

## Project summary

Vektor is a local-first, paper-only trading research application. A Next.js dashboard connects to a FastAPI backend to explore historical prices, inspect simulated portfolios, backtest strategies, compare configurations, and evaluate parameter grids on chronological train/test segments. Optional AI explanations interpret measured facts while leaving financial calculations in deterministic application code.

## Technologies

TypeScript, React 19, Next.js 16 App Router, Tailwind CSS 4, Motion, custom SVG charts, Python, FastAPI, Pydantic, `Decimal`, SQLite, `yfinance`, and the optional Anthropic SDK. Tooling includes npm, `uv`, pytest/HTTPX, Node's test runner, ESLint, and TypeScript checks.

## Engineering contributions represented in the repository

- **Financial integrity:** decimal accounting, explicit rounding, exact money formatting, atomic SQLite orders, and idempotency keys that prevent duplicate simulated fills.
- **Research engine:** Buy & Hold, SMA, and RSI backtests; next-open fills from prior-close signals; configurable costs; shared-data comparison; bounded parameter search ranked exclusively on training data.
- **Honest evaluation:** independent train/test segments, missing-metric handling, overfitting flags, and visible distinctions between simulated performance, measured facts, and AI interpretation.
- **Frontend systems:** typed and runtime-validated API clients, responsive results tables, keyboard-accessible interactive charts, stale-request cancellation, and memoized chart work and result sections.
- **Reliability and operations:** isolated provider tests, financial-output regression checks, workload limits, request IDs, structured logs, configurable CORS, and documented persistent-volume deployment and backups.

These describe implemented project work, not individual authorship, measured business impact, or production adoption. [Repository ownership rules](AGENTS.md) distinguish backend and frontend responsibilities.

## Resume description

Developed a paper-trading research application with Next.js, TypeScript, FastAPI, and SQLite, supporting historical strategy backtests, configuration comparisons, and bounded parameter optimization with chronological holdout evaluation. Implemented exact decimal accounting and idempotent simulated orders alongside typed API validation, interactive charts, and regression coverage. Integrated optional AI explanations grounded in locally measured backtest facts, with explicit unavailable states and backend-only credentials.

Use this description only to the extent it reflects your own contributions; narrow the scope for frontend-only or backend-only work.

## Scope and tradeoffs

This is educational software, not an execution platform or investment adviser. Market history depends on Yahoo Finance availability; optional Anthropic usage is paid. SQLite persistence and in-memory limits favor a single backend process, and the API has no authentication or multi-user isolation. Daily-bar simulations omit execution details; paper portfolios do not automatically adjust quantities for splits or credit dividends.

See the [README](README.md) for verified features, setup, architecture, API references, deployment prerequisites, and fuller limitations. No deployed URL, user count, profitability claim, or unverified performance achievement is asserted here.

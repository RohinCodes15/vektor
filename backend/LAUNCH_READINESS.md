# Launch readiness (Phase 5E)

Final verification before the first deployment, run on 2026-11-09 against commit `1969915` plus the Phase 5E fixes
below. Nothing was deployed and no paid resource was created. Every result here was observed in this run.

**Verdict: ready to deploy.** Every critical check passes. What remains are operator steps (an account, a domain, a
volume), not code defects. See "Before the first deploy".

## Checks

| Area | Check | Result |
|---|---|---|
| Backend tests | `uv run pytest` | PASS: 740 passed (727 before Phase 5E, plus 13 new) |
| Backend lint | `uvx ruff check .` (rules pinned in `pyproject.toml`) | PASS |
| Frontend | `npm run typecheck`, `npm run lint` | PASS |
| Frontend | `npm test` | PASS: 143 passed |
| Frontend | `NEXT_PUBLIC_API_ORIGIN=https://… npm run build` | PASS (static `/`) |
| Workflows, real Yahoo data | Market history, paper orders, analytics, backtests, AI insights (provider off), comparison, optimization | PASS: 32/32 |
| Security probes | Paper-only settings, CORS, headers, body and rate limits, safe errors, request ids | PASS: 21/21 |
| Production server | Real uvicorn in production mode, with temporary databases | PASS |
| Docker image | Built and run with a volume (colima) | PASS |
| Browser | Frontend dev server plus backend, in Chromium | PASS, with the notes below |

## Workflows (real Yahoo Finance data, temporary databases)

- **Market data:** AAPL 2023 returns 250 sessions, ordered, weekdays only, OHLC bounds hold. The second request comes
  from the cache with identical bars. An unknown symbol and a weekend-only range answer 404; nothing is filled in.
- **Paper trading:** buys fill at a real close, a resent `client_order_id` returns the original fill, an oversell and
  an overspend are rejected (422) and leave cash unchanged.
- **Analytics:** snapshots, equity history, analytics, allocation and risk all answer 200.
- **Backtests:** the same request gives identical results apart from id and time. A run cut off at 2019 is an exact
  prefix of the 2015–2024 run, equity curve and trades both, so no bar uses later data.
- **AI insights:** with the provider off (the default) the analysis returns measured facts only.
- **Comparison:** deterministic, and its SMA result equals a standalone backtest of the same strategy.
- **Optimization:** the training days strictly precede the test days and add up to all bars. The selected strategy's
  train and test metrics equal standalone backtests over exactly those days. Repeat runs are identical.
- **Guided demo (browser):** Explore Demo opens six steps; Next, Back, Finish, Skip and Escape work; focus returns to
  the entry button; the top-bar Demo guide link moves focus to the guide; the demo sends no requests to the backend.
- **Frontend and backend together (browser):** the status panel reports Connected. A 10-year SPY SMA backtest from the
  form returns 2,516 trading days and 45 fills. With the backend stopped, the status panel and the backtest form both
  say the backend could not be reached. At 390 px wide there is no horizontal scrolling.

## Production configuration

- Startup in production with no settings refuses to run and names `VEKTOR_CORS_ORIGINS`, `VEKTOR_PORTFOLIO_DB_PATH`
  and `VEKTOR_BACKTEST_DB_PATH`. The Docker image with only the `fly.toml` defaults names `VEKTOR_CORS_ORIGINS`.
- Health answers 200 with `trading_mode: paper`, HSTS, the deny-all CSP and a request id. `/docs` and `/openapi.json`
  answer 404. A preflight from the configured origin is allowed; one from another origin gets no allow-origin header.
- A portfolio, its fill and a stored backtest survive a server restart, and in Docker they survive replacing the
  container on the same volume. `python -m app.backup` copies the databases while the server runs.
- The container runs as the unprivileged `vektor` user (files on the volume are owned by uid 10001), its health check
  reports healthy, and it reaches Yahoo Finance from inside the container.

## Fixed in Phase 5E

**Rate limits could be dodged behind Fly.io (security).** `fly.toml` sets `FORWARDED_ALLOW_IPS="*"`. With `*`,
uvicorn 0.54 takes the leftmost `X-Forwarded-For` entry as the client, and the client writes that entry itself. Fly's
proxy appends the real address to the right. Sending a different `X-Forwarded-For` with each request therefore gave
every request a fresh rate-limit window. Reproduced on a real server: six requests over a limit of three, all 200.

The fix is a new setting, `VEKTOR_TRUSTED_PROXY_HOPS` (default `0`, set to `1` in `fly.toml` and the production env
example). With N trusted proxies, the rate limiter keys on the Nth `X-Forwarded-For` entry from the right, the one
the outermost trusted proxy appended, and ignores everything to its left. When the entry is missing or not an IP, it
falls back to the TCP peer. After the fix the same six requests answer 200, 200, 200, 429, 429, 429, and the Docker
image behaves the same way. Regression tests: `tests/test_middleware.py`, `tests/test_deployment.py` and
`tests/test_security_config.py`.

**Lint results depended on the ruff version.** There was no ruff configuration, and ruff 0.17 changed its defaults,
so a plain `ruff check` reported 24 style findings. `pyproject.toml` now pins the rules (the classic defaults, bugbear,
import order) and a 120-column line length.

No API contract changed and no dependency was added.

## Not verified here

- The real Anthropic provider: it is paid and off by default, so it was not called. Its request and error handling
  are covered by tests with a fake client.
- Yahoo Finance from Fly.io's network: it works locally and from a container, but cloud IPs can be throttled. Check
  after the first deploy with one history request.
- Screen readers and real phones: only keyboard behavior and a 390 px Chromium viewport were checked.


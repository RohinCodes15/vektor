# Launch readiness (Phase 5E)

Final verification before the first deployment, run on 2026-11-09 against commit `1969915` plus the Phase 5E fixes
below. Nothing was deployed and no paid resource was created. Every result here was observed in this run.

**Verdict: ready to deploy.** Every critical check passes. What remains are operator steps (an account, a domain, a
volume), not code defects. See "Before the first deploy".

## Live verification (Phase 5F)

Deployed on 2026-11-09: frontend https://vektor-paper.vercel.app, backend https://vektor-api.fly.dev. Before
deploying, Phase 5F found that the API let anyone list, change or delete every paper portfolio, and added public mode
with an owner key (see `DEPLOYMENT.md`). It also lowered the general rate limit to 60 a minute to bound bandwidth cost.

| Check (live, against the deployed services) | Result |
|---|---|
| Backend tests after the public mode change | PASS: 765 passed |
| Health, HTTPS redirect, HSTS, deny-all CSP, request id, `/docs` 404 | PASS |
| CORS: `https://vektor-paper.vercel.app` allowed, other origins refused | PASS |
| Yahoo Finance from Fly (AAPL January 2024, MSFT 2023: 250 sessions); unknown symbol 404 | PASS |
| Visitors cannot create, edit, delete, trade in or snapshot a portfolio, or list stored backtests (403) | PASS |
| Owner key: a showcase portfolio with three buys at real closes, a snapshot, an oversell rejected (422) | PASS |
| Visitors read holdings, transactions, equity history, analytics, allocation and risk | PASS |
| Backtest deterministic; a truncated run is an exact prefix (no look-ahead) | PASS |
| AI Insights with the provider off: measured facts, interpretation unavailable | PASS |
| Comparison equals a standalone backtest; optimization trains strictly before it tests | PASS |
| Oversized body 413; validation errors never echo input | PASS |
| Rate limit: 59 requests passed, then 429 with `Retry-After` and CORS, despite a new invented `X-Forwarded-For` on each | PASS |
| SQLite on the volume: the portfolio and its trades survive a machine restart; files owned by the unprivileged user | PASS |
| Browser, live site: Connected, showcase portfolio shown, favicon, requests only to the configured backend | PASS |
| Browser, live site: price chart (251 observations), backtest, AI Insights, comparison, optimization, guided demo | PASS |
| Browser, live site at 390 px after results load | **FAIL** (frontend): the page is 1,732 px wide |
| API checks through the live API script | 26/26 |

The 390 px failure: `.workspace` in `frontend/src/app/globals.css` is a grid with no column size, so its one implicit
column grows to the widest table once results load. Adding `grid-template-columns: minmax(0, 1fr);` to `.workspace`
was tested in the live page and brings it back to 375 px with nothing overflowing outside the tables' own scroll areas.

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
- Yahoo Finance from Fly.io over time: it worked in every live check, but cloud IPs can be throttled later.
- Screen readers and real phones: only keyboard behavior and a 390 px Chromium viewport were checked.

## Frontend notes for Codex (not blockers)

- Fixed by Codex: the favicon, and the stale "no backend connection required" line in `frontend/README.md`.
- Running `next dev` makes Next.js 16 generate an untracked `frontend/AGENTS.md`. Either commit it or add it to
  `.gitignore` (a coordinated root file) so it doesn't keep showing up as a stray file.

## Before the first deploy

These are operator steps; the details are in [`DEPLOYMENT.md`](DEPLOYMENT.md) and
[`../frontend/DEPLOYMENT.md`](../frontend/DEPLOYMENT.md).

1. Create a Fly.io account with a payment method (compute plus a 1 GB volume, a few dollars a month) and install
   `flyctl`. Choose the frontend host (the docs use Vercel) so you know its final https origin.
2. `cd backend && fly launch --no-deploy --copy-config --name <app>`, then
   `fly volumes create vektor_data --size 1 --region iad`.
3. In `fly.toml`, uncomment `VEKTOR_CORS_ORIGINS` and set the frontend origin. Keep `VEKTOR_TRUSTED_PROXY_HOPS = "1"`.
4. `fly deploy`, then `curl https://<app>.fly.dev/api/v1/health` and one history request to confirm Yahoo is reachable.
5. Build the frontend with `NEXT_PUBLIC_API_ORIGIN=https://<app>.fly.dev` and deploy it.
6. Schedule `fly ssh console --user vektor -C "python -m app.backup /data/backups"`, or keep volume snapshots.

There are no user accounts. Anyone who can reach the API can create and read paper portfolios and backtests. The
rate limits, body limit and concurrency cap bound the load; no real money or brokerage is involved.

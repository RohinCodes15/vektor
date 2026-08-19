# Deploying the Vektor backend (Phase 5A)

Vektor is **paper-only**. No setting, image, or manifest here enables a broker, real money, or order routing:
`VEKTOR_TRADING_MODE` accepts only `paper`, and unknown settings (a broker key, say) stop startup.

Nothing in this repository deploys anything or creates resources. Every command below is one you run yourself.

## What the backend needs

| Need | Why | Consequence |
|---|---|---|
| **One process** | Rate limits and the expensive-request cap are kept in memory; SQLite expects one writer | One machine, one uvicorn worker. No horizontal scaling. |
| **A persistent disk** | Paper portfolios (`VEKTOR_PORTFOLIO_DB_PATH`) and stored backtests (`VEKTOR_BACKTEST_DB_PATH`) are SQLite files | Without one, every restart or deploy erases them. The market data cache is disposable. |
| **Outbound HTTPS to Yahoo Finance** | Market data (free, no key). Yahoo may rate-limit or block some datacenter IP ranges | Market data calls return `503` while blocked. The on-disk cache softens repeat requests. |
| **Outbound HTTPS to Anthropic** (optional) | AI analysis, off by default (`VEKTOR_AI_PROVIDER=none`) | Paid per use. Without it, analysis returns the measured facts with an `unavailable` interpretation. |
| **About 512 MB RAM** | pandas and numpy (via yfinance) plus Decimal backtests | 256 MB VMs risk out-of-memory kills on 20-year optimizations. |
| **HTTPS in front** | HSTS is sent in production; CORS origins must be `https` | Use the platform's TLS-terminating proxy. |

## Recommended setup: Fly.io, one machine plus one volume

The Docker image (`backend/Dockerfile`) runs anywhere that runs containers. `backend/fly.toml` targets Fly.io because it
offers, at low cost, the one thing free tiers usually lack: a persistent volume attached to a single always-addressable
machine. The machine stops when idle (`auto_stop_machines`) and starts on the next request, so you pay mostly for time
in use.

**Expected cost (approximate; check fly.io/docs/about/pricing before relying on it):**
- shared-cpu-1x, 512 MB: about $3 to $4 a month if it ran all the time; less with auto-stop, plus a second or two of
  cold start on the first request after idling.
- 1 GB volume: about $0.15 a month. Fly keeps daily volume snapshots (5 days by default); extra snapshot storage may
  cost a little.
- Fly needs a payment method on file, and new organizations get no free allowance. Outbound traffic for an API this
  size is usually free or cents.
- Yahoo Finance: free. Anthropic: only if you turn AI analysis on, billed to your Anthropic account.

**Free alternative, with no persistence:** Render's free web service runs the same Dockerfile but has no persistent
disk and sleeps after about 15 minutes idle. Paper portfolios and backtests are lost on every restart, deploy, and
sleep. That is acceptable only for a throwaway demo. Startup still requires you to set the database paths explicitly
(for example `/tmp/portfolios.sqlite3`), so the data loss is a choice you make on purpose.

## Production configuration

`deploy/production.env.example` lists every production setting. In production, startup **fails with a message naming
each missing setting** (`app/startup.py`) when:
- `VEKTOR_CORS_ORIGINS` is not set. Give your frontend's exact `https` origins as a JSON list, or `[]` for no browser
  origin.
- `VEKTOR_PORTFOLIO_DB_PATH` or `VEKTOR_BACKTEST_DB_PATH` is not set. Their defaults are inside the image and vanish on
  deploy.
- `VEKTOR_AI_PROVIDER=anthropic` and neither `VEKTOR_AI_API_KEY` nor `ANTHROPIC_API_KEY` is set.
- A database directory cannot be created or written.

It also logs a warning if a rate limit is off, the docs are on, or no CORS origin is set. Phase 4A rules still apply:
production rejects `*` and plain-`http` origins (except localhost), turns the docs off, and keeps the limits.

| Variable | Where | Notes |
|---|---|---|
| `VEKTOR_CORS_ORIGINS` | `fly.toml` `[env]` | Not a secret. Required. |
| `VEKTOR_*_DB_PATH`, `VEKTOR_MARKET_DATA_CACHE_PATH` | `fly.toml` `[env]` (preset to `/data`) | Must be on the volume |
| `VEKTOR_AI_API_KEY` | `fly secrets set` only | Never in a file, a commit, or a log |
| `FORWARDED_ALLOW_IPS` | `fly.toml` `[env]` (preset to `*`) | Read by uvicorn. `*` is safe only when the platform proxy is the only way in. Otherwise all clients share one rate limit, or clients can spoof their IP. |

## Deploying to Fly.io

Prerequisites: the `flyctl` CLI, a Fly account, and the frontend's final https origin.

```bash
cd backend
fly launch --no-deploy --copy-config --name <your-app-name>       # keeps fly.toml; update `app` if asked
fly volumes create vektor_data --size 1 --region iad               # one volume, same region as primary_region
# Edit fly.toml: uncomment VEKTOR_CORS_ORIGINS and set your frontend's origin(s).
fly secrets set VEKTOR_AI_API_KEY=...                              # only if you set VEKTOR_AI_PROVIDER=anthropic
fly deploy
curl https://<your-app-name>.fly.dev/api/v1/health                 # {"status":"ok",...,"trading_mode":"paper"}
```

Then point the frontend at it with `NEXT_PUBLIC_API_ORIGIN=https://<your-app-name>.fly.dev`.

Check the deployment:
- `fly logs` shows one JSON line per request (no query strings), and `app configured` with `environment: production`.
- `fly status` shows one machine passing the `/api/v1/health` check.
- A market history request returns data. A steady `503` means Yahoo is refusing the host's IPs; see Limitations.

Run it locally the same way:

```bash
docker build -t vektor-backend backend
docker run --rm -p 8000:8000 -v vektor_data:/data \
  -e VEKTOR_CORS_ORIGINS='["http://localhost:3000"]' \
  -e VEKTOR_PORTFOLIO_DB_PATH=/data/portfolios.sqlite3 -e VEKTOR_BACKTEST_DB_PATH=/data/backtests.sqlite3 \
  -e VEKTOR_MARKET_DATA_CACHE_PATH=/data/market_data.sqlite3 vektor-backend
```

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

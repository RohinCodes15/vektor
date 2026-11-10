# Deploying the Vektor backend (Phase 5A)

Vektor is **paper-only**. No setting, image, or manifest here enables a broker, real money, or order routing:
`VEKTOR_TRADING_MODE` accepts only `paper`, and unknown settings (a broker key, say) stop startup.

Nothing in this repository deploys anything or creates resources. Every command below is one you run yourself.

## Live deployment (Phase 5F)

Deployed and verified on 2026-11-09:

| | |
|---|---|
| Frontend | https://vektor-paper.vercel.app (Vercel project `vektor-paper`, Hobby, Root Directory `frontend`) |
| Backend | https://vektor-api.fly.dev ([health](https://vektor-api.fly.dev/api/v1/health)), Fly app `vektor-api` |
| Machine | one shared-cpu-1x, 512 MB, region `iad`, stops when idle |
| Storage | volume `vektor_data`, 1 GB, encrypted, at `/data`, with daily snapshots kept 5 days |
| Network | shared IPv4 and IPv6 (no dedicated IPv4) |
| AI | off (`VEKTOR_AI_PROVIDER=none`); no AI key is set |
| Owner key | Fly secret `VEKTOR_OWNER_KEY`; a copy is kept outside the repository at `~/.config/vektor/owner_key` |

Expected cost: up to $3.69 a month for the machine if it never stops, plus $0.15 for the volume. Fly waives a personal
organization's bill under $5 a month (per its pricing page on 2026-11-09). What could raise it: outbound bandwidth at
$0.02/GB, a second machine (`fly deploy` on a new app creates two unless `--ha=false`), a dedicated IPv4 ($2/month), or
a larger VM. The Vercel project deploys every push to `main` automatically.

### Public mode and the owner key

The API has no user accounts, so the public deployment runs in **public mode** (the production default):
- Anyone can read paper portfolios and run, read and analyze backtests, comparisons and optimizations.
- Creating, editing or deleting portfolios, placing orders, recording snapshots, and listing every stored backtest
  answer `403` unless the request carries the owner key in `X-Vektor-Owner-Key`.

Using the key from your machine, without putting it in your shell history:

```bash
curl -X POST https://vektor-api.fly.dev/api/v1/portfolios -H 'content-type: application/json' \
  -H "X-Vektor-Owner-Key: $(cat ~/.config/vektor/owner_key)" -d '{"name":"My portfolio","starting_cash":"10000.00"}'
```

To rotate it: write a new random value to the file, then
`printf 'VEKTOR_OWNER_KEY=%s\n' "$(cat ~/.config/vektor/owner_key)" | fly secrets import -a vektor-api`.

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

It also logs a warning if a rate limit is off, the docs are on, no CORS origin is set, public mode is off, or public
mode has no owner key. Phase 4A rules still apply:
production rejects `*` and plain-`http` origins (except localhost), turns the docs off, and keeps the limits.

| Variable | Where | Notes |
|---|---|---|
| `VEKTOR_CORS_ORIGINS` | `fly.toml` `[env]` | Not a secret. Required. |
| `VEKTOR_*_DB_PATH`, `VEKTOR_MARKET_DATA_CACHE_PATH` | `fly.toml` `[env]` (preset to `/data`) | Must be on the volume |
| `VEKTOR_AI_API_KEY` | `fly secrets set` only | Never in a file, a commit, or a log |
| `VEKTOR_TRUSTED_PROXY_HOPS` | `fly.toml` `[env]` (preset to `1`) | How many proxies append to `X-Forwarded-For`. Rate limits key on the address the outermost one appended. With `0` behind a proxy, every client shares one limit. |
| `FORWARDED_ALLOW_IPS` | `fly.toml` `[env]` (preset to `*`) | Read by uvicorn for the request scheme. It does not choose the rate-limit address: with `*`, uvicorn takes the leftmost `X-Forwarded-For` entry, which the client can write. |

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

## Backups and rollback

**Before every deploy, back up the data.** A deploy can migrate the SQLite schema forward. Phase 4B added a summary
column, for example. Older code is not guaranteed to read a migrated file.

```bash
fly ssh console --user vektor -C "python -m app.backup /data/backups"    # consistent copy while serving
fly volumes snapshots create <volume-id>                                 # platform snapshot (fly volumes list)
```

`app.backup` uses SQLite's online backup API, so it never captures a half-written order. Add `--include-cache` to copy
the market data cache too.

**Roll back the code** (data untouched):

```bash
fly releases --image                       # find the last good image
fly deploy --image <registry.fly.io/app:deployment-...>
```

**Roll back the data** too, when the new release migrated or damaged it:
1. Stop traffic: `fly scale count 0`.
2. Restore the files: `fly ssh console` into a machine with the volume and copy `/data/backups/<timestamp>/*.sqlite3`
   over `/data/`. Or create a volume from a snapshot (`fly volumes create vektor_data --snapshot-id <id> --region iad`)
   and attach it in place of the damaged one.
3. Deploy the matching image (above), then `fly scale count 1`, and check `/api/v1/health` plus a portfolio read.

Anything created after the backup is lost by a data rollback. Paper orders are simulated, so nothing real is ever at
stake.

## Limitations and remaining risks

- **No authentication.** Anyone who can reach the URL can create and change paper portfolios. CORS limits browsers
  only. Do not share the URL with people you do not trust. An auth layer is future work.
- **Yahoo Finance availability.** It is unofficial and free, with undocumented rate limits, and some cloud IP ranges
  get blocked. Expect occasional `503`s. Vektor never fabricates data to cover gaps.
- **Single machine.** A restart, deploy, or idle stop interrupts in-flight requests, and the in-memory rate limits reset.
- **Cold starts.** With auto-stop, the first request after idling waits for the machine to boot.
- **Image size.** About 950 MB, mostly pandas and numpy through yfinance. That is fine for Fly but slow on very
  constrained builders.
- **Health check.** `/api/v1/health` is liveness only: it does not open the databases or call Yahoo. Startup itself
  verifies configuration and storage.

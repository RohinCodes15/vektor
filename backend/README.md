# Vektor backend

FastAPI service for Vektor, a local-first, paper-only trading simulator. See `../AGENTS.md` for the architecture and ownership rules.

## Requirements

- [uv](https://docs.astral.sh/uv/). It installs Python 3.13 automatically from `.python-version`.

## Setup and run

```bash
cd backend
uv sync                          # create .venv and install deps (incl. dev)
cp .env.example .env             # optional; every setting has a default
uv run uvicorn app.main:app --reload
curl localhost:8000/api/v1/health
```

Interactive API docs: http://localhost:8000/docs

## Tests

```bash
uv run pytest
```

## Configuration

All settings are `VEKTOR_*` environment variables or keys in `backend/.env` (see `.env.example`). Unknown keys in `.env` are rejected. `VEKTOR_TRADING_MODE` only accepts `paper`. `VEKTOR_MARKET_DATA_CACHE_PATH` and `VEKTOR_MARKET_DATA_CACHE_TTL_HOURS` (1 to 8760) control the market data cache.

## Historical market data (Phase 2A)

Read-only daily OHLCV prices from Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance): free, no account, no API key. Nothing here places orders or touches a broker.

```bash
curl "localhost:8000/api/v1/market/history?symbol=AAPL&start=2024-01-01&end=2024-01-31"
```

| Parameter | Required | Rules |
|-----------|----------|-------|
| `symbol` | yes | Yahoo ticker, case-insensitive, 1-15 of letters, digits, `.`, `-`, `=`, optional leading `^` (`AAPL`, `BRK-B`, `^GSPC`, `EURUSD=X`, `7203.T`). Normalized to upper case. |
| `start`, `end` | yes | Inclusive `YYYY-MM-DD` dates. `start <= end`, and `start` cannot be in the future. `end` may be in the future; only existing bars are returned. |
| `interval` | no | `1d` (the only supported interval). |

Unknown parameters are rejected. A successful response (`MarketHistoryResponse` in `app/contracts.py`):

```json
{
  "symbol": "AAPL", "interval": "1d", "start": "2024-01-01", "end": "2024-01-31",
  "currency": "USD", "source": "yahoo_finance", "cached": false,
  "fetched_at": "2026-09-23T15:04:05.123456Z",
  "bars": [
    {"date": "2024-01-02", "open": 187.15, "high": 188.44, "low": 183.89, "close": 185.64,
     "adjusted_close": 183.40, "volume": 82488700}
  ]
}
```

- `date` is the trading day in the exchange's local calendar. Bars are ascending, one per date.
- `open`/`high`/`low`/`close` are as Yahoo reports them (split-adjusted). `adjusted_close` also reflects dividends.
- `currency` is Yahoo's code, verbatim (`GBp` means pence), or `null` if Yahoo did not report one.
- `cached` says whether the response came from the local cache. `fetched_at` is when Yahoo returned the data.

Every error is `{"detail": "<message>"}`:

| Status | Meaning |
|--------|---------|
| 422 | Invalid symbol, dates, interval, or unknown parameter. The provider is not called. |
| 404 | No bars for the symbol and range: unknown symbol, or no trading days (e.g. a weekend). |
| 502 | Yahoo returned invalid data: missing values, duplicate dates, non-positive or non-finite prices, `high`/`low` that do not bound `open`/`close`, or negative or fractional volume. The whole response is rejected. |
| 503 | Yahoo could not be reached, timed out (10 s), or rate-limited the request. |

### Data integrity

Market data is never fabricated, filled, interpolated, or repaired. A response is either Yahoo's data, validated bar by bar, or an error. Rows that yfinance returns entirely empty (no prices and no volume) are dropped by yfinance itself, so those dates are simply absent.

### Cache

Responses are cached in SQLite at `backend/data/market_data.sqlite3` (git-ignored; set `VEKTOR_MARKET_DATA_CACHE_PATH` to move it). Each entry is one complete Yahoo response. A request is served from the cache only when a single entry fetched within `VEKTOR_MARKET_DATA_CACHE_TTL_HOURS` (default 24) covers its whole range, so history is never stitched together from fetches made at different times. Repeated and narrower requests are served locally; wider ones are fetched again.

Ranges that end today (UTC) or later are never cached, because today's bar may still change. Cache read or write failures are logged and fall back to Yahoo; they never fail a request. To clear the cache, stop the server and delete the file.

### Limitations

- Yahoo Finance is an unofficial, free source with no uptime guarantee and undocumented rate limits. Its data can contain errors; 502 responses surface the ones that fail validation.
- yfinance reports a missing daily volume as `0`, so a zero volume cannot be told apart from an unreported one.
- Yahoo restates split- and dividend-adjusted values after corporate actions. A cached entry can lag such a restatement by up to the cache TTL.
- Only daily bars are supported. Requests are made synchronously, one symbol at a time.
- yfinance keeps its own small timezone cache in the user cache directory.
- yfinance 1.7 emits `Pandas4Warning` deprecation warnings with pandas 3.1. They are harmless.

Tests mock the provider and use temporary cache files; `uv run pytest` makes no network requests.

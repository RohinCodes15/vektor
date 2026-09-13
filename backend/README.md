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

All settings are `VEKTOR_*` environment variables or keys in `backend/.env` (see `.env.example`). Unknown keys in `.env` are rejected. `VEKTOR_TRADING_MODE` only accepts `paper`. `VEKTOR_MARKET_DATA_CACHE_PATH` and `VEKTOR_MARKET_DATA_CACHE_TTL_HOURS` (1 to 8760) control the market data cache. `VEKTOR_PORTFOLIO_DB_PATH` sets where paper portfolios are stored (default `backend/data/portfolios.sqlite3`).

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

## Paper portfolios (Phase 2C)

Simulated portfolios funded with virtual US dollars. Orders fill against real daily closes from the market data engine above. **Paper only:** no order leaves this app, and there are no broker connections or credentials.

| Method and path (under `/api/v1`) | Does | Success |
|-----------------------------------|------|---------|
| `POST /portfolios` | Create from `{"name", "starting_cash"}` | 201 `Portfolio` |
| `GET /portfolios` | List all, oldest first | 200 `Portfolio[]` |
| `GET /portfolios/{id}` | One portfolio: cash, starting cash, realized P&L | 200 `Portfolio` |
| `PATCH /portfolios/{id}` | Rename: `{"name"}` is the only editable field | 200 `Portfolio` |
| `DELETE /portfolios/{id}` | Delete with its holdings and transaction history | 204 |
| `GET /portfolios/{id}/holdings` | Valuation: cash, position values, equity, unrealized and realized P&L, allocation | 200 `PortfolioHoldings` |
| `POST /portfolios/{id}/orders` | Submit a market order (`PaperOrder`) | 201 `Transaction`, or 200 on replay |
| `GET /portfolios/{id}/transactions` | Every executed order, oldest first | 200 `Transaction[]` |

```bash
curl -X POST localhost:8000/api/v1/portfolios -H 'content-type: application/json' \
  -d '{"name": "Growth", "starting_cash": "10000"}'
curl -X POST localhost:8000/api/v1/portfolios/<id>/orders -H 'content-type: application/json' \
  -d '{"client_order_id": "3f1c0f7e-0001", "symbol": "AAPL", "side": "buy", "quantity": "5"}'
curl localhost:8000/api/v1/portfolios/<id>/holdings
```

Contracts are in `app/contracts.py` (`PortfolioCreate`, `PortfolioUpdate`, `Portfolio`, `PaperOrder`, `Transaction`, `Holding`, `PortfolioHoldings`). Every amount is a JSON **string** holding a decimal (`"1000.00"`), so no precision is lost to floating point. Requests accept strings or numbers.

### Orders

- `symbol`: a ticker of 1-15 letters, digits, `.` or `-`, normalized to upper case. Indices (`^GSPC`), futures (`GC=F`) and currency pairs (`EURUSD=X`) are rejected because they have no share price.
- `side`: `buy` or `sell`. `quantity`: greater than 0, at most 6 decimal places (fractional shares allowed), at most 10 integer digits.
- `client_order_id`: required, 1-64 of letters, digits, `_ . : -`; a UUID is a good choice. It is unique per portfolio. Resending the same id with the same symbol, side and quantity returns the original transaction with status 200 and executes nothing, even when market data is unavailable. Reusing it for a different order returns 409.
- **Price:** the most recent completed daily `close` (split-adjusted, as Yahoo reports it) among the 14 days before today (UTC). Today's bar is never used, because it changes while markets are open. `price_date` records which day's close was used. Completed-day prices are served from the market data cache, so orders on the same day share one price.
- **Only USD:** the instrument's reported currency must be `USD`. Any other currency (or none reported) is rejected; nothing is converted.
- Orders fill completely or not at all. No fees, commissions or slippage. No short selling, margin, or limit orders.

### Validation and errors

Nothing is executed unless the whole order succeeds. Every error is `{"detail": "<message>"}`.

| Status | Meaning |
|--------|---------|
| 404 | Portfolio not found. |
| 409 | `client_order_id` already used for a different order in this portfolio. |
| 422 | Invalid body or id; untradable or malformed symbol; no daily close in the last 14 days (unknown, delisted or halted symbol); not priced in USD; **insufficient cash**; **overselling** or selling a symbol not held; buy worth less than $0.01. |
| 502 / 503 | Market data provider returned invalid data / was unreachable. The order is not executed. |

### Money and rounding

All arithmetic uses Python `Decimal`; floats never touch balances. Rounding is `ROUND_HALF_EVEN` (banker's rounding), applied once per computed value:

| Value | Rule |
|-------|------|
| Execution and valuation price | Provider close rounded to 4 decimal places |
| Notional (cash moved by a trade) | `quantity × price`, rounded to cents |
| Starting cash | At most 2 decimal places, stored in cents |
| Cost basis | Average cost. Buys add the notional. A partial sell removes `cost_basis × sold / held`, rounded to cents; a full sell removes the whole remaining basis |
| Realized P&L (per sell) | `notional − cost basis removed` |
| Market value | `quantity × latest close`, rounded to cents |
| Unrealized P&L | `market value − cost basis` |
| Equity | `cash + Σ market value` |
| Allocation % | `value / equity × 100`, rounded to 2 places. Rounded independently, so the allocations may not sum to exactly 100 |

### Valuation never guesses

`GET /holdings` prices each position at its latest completed close. If a held symbol has no close in the last 14 days, its price fields are `null`, and so are `positions_value`, `equity`, `unrealized_pnl` and every allocation, because they cannot be known. Cash, quantity, cost basis and realized P&L are always reported. A provider outage fails the request (502/503) instead of returning partial numbers. A cash-only portfolio needs no market data.

### Storage and integrity

Portfolios, positions and transactions are stored in SQLite at `VEKTOR_PORTFOLIO_DB_PATH`, separate from the disposable market data cache. **Deleting this file deletes every portfolio.** Amounts are stored as decimal text and round-trip exactly. Each order runs in one `BEGIN IMMEDIATE` transaction: the duplicate check, the cash and quantity checks and every write happen under SQLite's write lock, so concurrent requests cannot overdraw cash, oversell, or execute the same `client_order_id` twice. Any failure rolls the whole order back. Cash moves only through orders; `PATCH` cannot edit balances.

### Limitations

- Prices are daily closes, up to a day old: there are no intraday quotes. An order placed on day D fills at the last close before D, so buying and selling on the same day nets zero.
- Corporate actions are not applied. Yahoo restates historical closes after a split, but stored quantities and cost basis are not adjusted, so a position held across a split is valued incorrectly. Dividends are not credited.
- If a held symbol is delisted, it cannot be valued or sold (there is no price), so the portfolio's totals stay `null` until a price is available again.
- One currency (USD); no FX conversion.
- Valuation fetches each held symbol separately (cached for the day). List endpoints are not paginated, which is fine for local, single-user use.

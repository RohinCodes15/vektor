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

All settings are `VEKTOR_*` environment variables or keys in `backend/.env` (see `.env.example`). The optional AI analysis settings (`VEKTOR_AI_*`) are described under Phase 3A.1 below. Unknown keys in `.env` are rejected. `VEKTOR_TRADING_MODE` only accepts `paper`. `VEKTOR_MARKET_DATA_CACHE_PATH` and `VEKTOR_MARKET_DATA_CACHE_TTL_HOURS` (1 to 8760) control the market data cache. `VEKTOR_PORTFOLIO_DB_PATH` sets where paper portfolios are stored (default `backend/data/portfolios.sqlite3`). `VEKTOR_BACKTEST_DB_PATH` sets where backtest results are stored (default `backend/data/backtests.sqlite3`).

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

## Portfolio analytics (Phase 2E.1)

Equity history and performance metrics for paper portfolios. Every value comes from a recorded snapshot of actual simulated cash, holdings, and completed daily closes. Nothing is backfilled, interpolated, or estimated.

| Method and path (under `/api/v1`) | Does | Success |
|-----------------------------------|------|---------|
| `POST /portfolios/{id}/snapshots` | Record equity now, valued at the latest completed closes | 201 `EquitySnapshot` |
| `GET /portfolios/{id}/equity-history` | Every recorded snapshot, oldest first | 200 `EquitySnapshot[]` |
| `GET /portfolios/{id}/analytics` | Metrics from the recorded snapshots (no market data requests) | 200 `PortfolioAnalytics` |

### Snapshots

- Creating a portfolio records its first snapshot: all cash, so its equity is exactly the starting cash and needs no price. Portfolios created before Phase 2E.1 have no snapshots until one is recorded.
- `POST /snapshots` reads cash and positions together in one database transaction, then values each holding exactly like `GET /holdings` (latest completed close in the 14 days before today, USD only). It stores `cash`, `positions_value`, `equity`, `net_deposits`, `realized_pnl`, `unrealized_pnl`, and `prices_as_of`, the oldest close date used (`null` for a cash-only portfolio).
- If any holding has no recent price, the snapshot is refused with 422 and nothing is stored. A provider failure returns 502/503 and nothing is stored. A cash-only portfolio needs no market data.
- Snapshots are taken on request; Vektor does not record them on a schedule. Record one per day (for example after the US close) to build a daily history.
- Deleting a portfolio deletes its snapshots.

### Metrics and assumptions

Analytics are computed from snapshots only, as of the latest snapshot (`as_of`). A metric is `null` when there is not enough history for it.

| Metric | Definition | Needs |
|--------|------------|-------|
| `equity`, `net_deposits`, `realized_pnl`, `unrealized_pnl` | From the latest snapshot | 1 snapshot |
| `total_return_pct` | `equity / net_deposits − 1` | 1 snapshot |
| `latest_daily_return_pct` | Return from the previous daily observation to the latest | 2 daily observations |
| `volatility_pct` | Sample standard deviation of daily returns × √252 (annualized) | 2 daily returns |
| `sharpe_ratio` | Mean daily return ÷ sample standard deviation × √252; risk-free rate 0 | 2 daily returns, non-zero volatility |
| `max_drawdown_pct` | Largest fall from a running peak of the deposit-adjusted equity index; `0` or negative | 1 daily return |

- **Daily observations:** the last snapshot of each UTC calendar day. Days without a snapshot are absent, not filled, so a return can span several days; √252 annualization assumes one observation per trading day.
- **Daily return:** `(equity − deposits added since the previous observation) / previous equity − 1`. An observation that follows zero equity has no return and is skipped.
- **Deposits:** `net_deposits` is the external cash put into the portfolio. Today that is only the starting cash (there are no deposit or withdrawal endpoints), so returns already exclude it; the formula keeps later deposits from counting as gains.
- **Zero volatility:** `volatility_pct` is `0.0000` and `sharpe_ratio` is `null` (undefined).
- **Empty portfolios:** a cash-only portfolio has flat equity: 0% returns, 0% volatility, no Sharpe ratio, 0% drawdown.
- **Rounding:** percentages and the Sharpe ratio have 4 decimal places, `ROUND_HALF_EVEN`. All arithmetic is `Decimal`.

### Limitations

- History starts at portfolio creation and grows only as snapshots are recorded; past values are never reconstructed.
- Snapshot equity uses completed daily closes, so it lags the market by up to a day and inherits the corporate-action limitation above.
- Volatility and Sharpe ratio from a handful of observations are statistically weak. The response reports `daily_observations` so clients can judge.

## Allocation and risk (Phase 2F.1)

Current allocation, concentration, and return-based risk for a paper portfolio's actual holdings. Values come from the latest completed daily closes and the daily history Yahoo reports. Nothing is estimated. When the data is not enough, the response says `"status": "unavailable"` and gives an `unavailable_reason`, and the affected metrics are `null`.

| Method and path (under `/api/v1`) | Does | Success |
|-----------------------------------|------|---------|
| `GET /portfolios/{id}/allocation` | Weight of each asset and of cash, top holding, HHI | 200 `PortfolioAllocation` |
| `GET /portfolios/{id}/risk` | Portfolio volatility, each asset's contribution, pairwise correlations | 200 `PortfolioRisk` |

Errors are the same as `GET /holdings`: 404 for an unknown portfolio, 422 for an invalid id, and 502/503 when the provider returns invalid data or is unreachable. A provider failure is an error, never a partial result. Contracts: `PortfolioAllocation`, `AssetAllocation`, `PortfolioRisk`, `AssetRisk`, `AssetCorrelation` in `app/contracts.py`. Percentages, the HHI, and correlations have 4 decimal places, `ROUND_HALF_EVEN`. All arithmetic uses `Decimal`.

### Allocation formulas

Holdings are valued exactly like `GET /holdings`: `market value = quantity × latest completed close`, and `equity = cash + Σ market value`.

| Field | Formula |
|-------|---------|
| `weight_pct` | `market value / equity × 100`. Cash counts as an asset, so the asset weights plus `cash_weight_pct` make 100 (before rounding) |
| `cash_weight_pct` | `cash / equity × 100` |
| `position_weight_pct` | `market value / positions value × 100`: share of the invested amount, cash excluded |
| `top_holding_pct` | The largest `position_weight_pct`. On a tie, the alphabetically first symbol |
| `hhi` | Herfindahl-Hirschman index `Σ wᵢ²`, where `wᵢ` are position weights as fractions (cash excluded). It runs from `1/N` (N equal positions) to `1` (one position). Computed from unrounded weights |

- **Missing price:** if any holding has no close in the last 14 days, it is listed in `unpriced_symbols`, `equity` is unknown, and every weight is `null` (status `unavailable`). Weights are never computed from a partial valuation.
- **Cash only:** `cash_weight_pct` is `100` and `assets` is empty. Concentration is undefined, so the status is `unavailable`.
- **Zero value:** with zero equity, every weight is `null`. A position whose value rounds to $0.00 gives no position weights.
- **Stale prices:** a close more than 4 calendar days before today (UTC) sets `stale: true` on that asset and lists the symbol in `stale_symbols`. Four days covers a weekend plus a market holiday. Stale prices are still the latest real closes, so the weights are still reported. `prices_as_of` is the oldest close date used.

### Risk formulas

The window is the 120 calendar days before today, ending yesterday (UTC), which is about 80 trading days.

1. **Aligned returns:** keep only the dates on which every held symbol has a bar. A daily return is `adjusted_close on one aligned date / adjusted_close on the previous aligned date − 1`, so it includes splits and dividends. A day missing for one symbol is dropped for all of them, never filled, and the next return spans the gap for every symbol alike.
2. **Covariance `S`:** sample covariance (divided by n − 1) of the aligned daily returns.
3. **Weights `w`:** current `market value / equity`. Cash is part of equity with zero variance, so it lowers portfolio volatility.
4. `portfolio_volatility_pct = √(wᵀ S w) × √252 × 100`, annualized.
5. `volatility_contribution_pct` for asset i is `wᵢ (S w)ᵢ / √(wᵀ S w) × √252 × 100`. The contributions add up to the portfolio volatility. `contribution_share_pct` is the contribution divided by the portfolio volatility, times 100, and the shares add up to 100. A negative contribution means the asset hedges the others. Both are `null` when portfolio volatility is zero.
6. `volatility_pct` is the asset's own annualized volatility, `√Sᵢᵢ × √252 × 100`.
7. `correlation` is `Sᵢⱼ / √(Sᵢᵢ Sⱼⱼ)` for each pair of holdings. It is `null` when either series is constant.

Risk metrics are `available` only when **all** of these hold. Otherwise `unavailable_reason` gives the first one that fails:

- Every holding has a recent price (no price means weights are unknown).
- The portfolio holds at least one position. Cash alone has no asset returns.
- Equity is positive.
- Every holding has daily history in the window.
- There are at least **20** aligned daily returns (`min_observations`). `observations` reports how many were found.
- The latest aligned date (`returns_as_of`) is no more than 4 calendar days old.

### Assumptions and limitations

- Risk uses the current quantities as if they had been held through the whole window. Past trades are not replayed, so this measures the risk of the portfolio as it is now, not its realized history (see Phase 2E.1 analytics for that).
- Covariance from 20 to 80 observations is noisy, and √252 annualization assumes one return per trading day.
- Weights use the split-adjusted `close`, while returns use `adjusted_close`. A recent corporate action can make the two disagree until stored quantities are adjusted (see the Phase 2C limitation).
- Each held symbol's history is fetched once per day and then served from the market data cache.

## Strategy backtests (Phase 2G.1)

Paper-only simulations of a trading strategy on real completed daily history from the market data service. Nothing is sent to a broker, and no price is invented: a backtest with an unknown symbol, non-USD prices, or too little history is rejected and nothing is stored.

| Method and path (under `/api/v1`) | Does | Success |
|-----------------------------------|------|---------|
| `POST /backtests` | Run a backtest and store the result | 201 `Backtest` |
| `GET /backtests` | List stored backtests, oldest first, without curves and trades | 200 `BacktestSummary[]` |
| `GET /backtests/{id}` | One stored backtest | 200 `Backtest` |

```bash
curl -X POST localhost:8000/api/v1/backtests -H 'content-type: application/json' -d '{
  "symbols": ["AAPL", "MSFT"], "start": "2023-01-01", "end": "2024-12-31", "starting_cash": "10000",
  "strategy": {"kind": "sma_crossover", "fast_window": 20, "slow_window": 50},
  "position_size_pct": "100", "fee_per_trade": "1.00", "fee_bps": "0", "slippage_bps": "5"
}'
```

Errors are `{"detail": "..."}`: 422 for an invalid request, unknown symbol, non-USD prices, or too little history; 404 for an unknown backtest id; 502/503 when the provider returns invalid data or cannot be reached. Contracts: `BacktestCreate`, the strategy models, `Backtest`, `BacktestSummary`, `BacktestMetrics`, `BacktestTrade`, `BacktestRejectedOrder`, `BacktestEquityPoint`, `BacktestPosition` in `app/contracts.py`. Money is a `Decimal` serialized as a string, in cents; prices have 4 decimal places; percentages and the Sharpe ratio have 4.

### Request

| Field | Meaning |
|-------|---------|
| `symbols` | 1 to 10 distinct tradable tickers (no indices, futures, or currency pairs) |
| `start`, `end` | Inclusive calendar dates, `start` before `end`, `end` before today (UTC): only completed bars are simulated |
| `starting_cash` | Virtual USD, more than 0, at most 2 decimal places |
| `strategy` | One of the strategies below, chosen by `kind` |
| `position_size_pct` | Share of equity each entry targets, split equally across the symbols. Default 100 |
| `fee_per_trade` | Fixed dollars per fill, 0 to 1000. Default 0 |
| `fee_bps` | Commission in basis points of each fill's notional, 0 to 1000. Default 0 |
| `slippage_bps` | Basis points every fill price moves against the trade, 0 to 1000. Default 0 |

### Strategies

Signals are computed at a bar's close from that close and earlier closes only.

| `kind` | Parameters | Rule |
|--------|------------|------|
| `buy_and_hold` | none | Buy every symbol at the first bar; never sell |
| `sma_crossover` | `fast_window` (2 to 250, default 20) < `slow_window` (3 to 500, default 50) | Buy when the fast simple moving average crosses above the slow one (`fast − slow` goes from ≤ 0 to > 0); sell when it crosses below (from ≥ 0 to < 0) |
| `rsi` | `period` (2 to 100, default 14), `oversold` (default 30) < `overbought` (default 70), both between 0 and 100 | Wilder's RSI: buy while RSI < `oversold`, sell while RSI > `overbought` |

`SMA(n)` at bar i is the mean of the last n closes. Wilder's RSI uses changes `cₖ = closeₖ − closeₖ₋₁`: the first average gain and loss are simple means over the first n changes, then `average = (previous × (n − 1) + current) / n`; `RSI = 100 − 100 / (1 + average gain / average loss)`, 100 when there are no losses, and undefined (no signal) when prices did not move. A buy signal while holding the symbol and a sell signal while flat are ignored.

**Minimum history:** the first possible signal must be able to fill, so a backtest needs at least 2 trading days for buy & hold, `slow_window + 2` for SMA crossover, and `period + 2` for RSI. Indicators warm up inside the requested range; no data before `start` is used.

### Simulation

1. **Prices:** every bar is converted to split- and dividend-adjusted prices: open, high, low, and close are multiplied by `adjusted_close / close` and rounded to 4 places. Fills, positions, and the equity curve use these prices, so a split or dividend never shows up as a gain or loss. Trade prices are therefore adjusted prices, not the literal historical quotes.
2. **Calendar:** only dates on which every symbol has a bar are simulated (`bars`). A date missing for one symbol is dropped for all of them, never filled.
3. **No look-ahead:** a signal at the close of day t fills at the **open of the next simulated day**. A signal on the last day never fills. Each day: fill yesterday's orders at the open (sells first, then buys, each in symbol order), mark positions at the close, then compute signals.
4. **Fill price:** buys pay `open × (1 + slippage)`, rounded up to 4 places and capped at the day's high; sells receive `open × (1 − slippage)`, rounded down and floored at the day's low. A fill never happens outside the day's traded range.
5. **Fees:** `fee_per_trade + notional × fee_bps / 10000`, rounded to cents, on every fill. `notional = quantity × price`, rounded to cents.
6. **Sizing and cash:** long only, whole shares. A buy targets `equity at the previous close × position_size_pct / 100 / number of symbols`, limited to the cash on hand, and buys the largest whole quantity whose notional plus fee fits. A sell closes the whole position. An order that cannot fill (less than one share affordable, or a sell whose fee would exceed its proceeds plus cash) appears in `rejected_orders` with a reason and changes nothing. Cash never goes negative.
7. **End:** positions still held after the last day are not sold. They are reported in `open_positions`, marked at the last adjusted close, and counted in the final equity.

The simulation is deterministic: the same request on the same market data gives the same result (only `id` and `created_at` differ). Results are stored whole and returned unchanged by `GET`; they are never recomputed.

### Metrics

`E₀ … Eₙ` is the equity at each day's close (`E₀` is the starting cash, since nothing fills on the first day).

| Field | Formula | Undefined (`null`) when |
|-------|---------|-------------------------|
| `total_return_pct` | `Eₙ / starting cash − 1` | never |
| `annualized_return_pct` | `(Eₙ / starting cash)^(252 / n) − 1`, n = number of daily returns; −100 if equity reaches 0 | fewer than 1 daily return, or the result exceeds 10²² % (a large gain over very few days, too big for 4 decimal places) |
| `volatility_pct` | sample standard deviation of daily returns `Eₜ / Eₜ₋₁ − 1` × √252 | fewer than 2 daily returns |
| `sharpe_ratio` | mean daily return / sample standard deviation × √252, risk-free rate 0 | fewer than 2 daily returns, or zero volatility (for example, nothing was bought) |
| `max_drawdown_pct` | lowest `Eₜ / max(E₀ … Eₜ) − 1`; each `equity_curve` point has its own `drawdown_pct` | never |
| `win_rate_pct` | sells with `realized_pnl > 0` / all sells | no trade was closed |

`realized_pnl` of a sell is `notional − fee − (buy notional + buy fee)`, so fees on both legs count. `total_fees` adds every fee. Each `null` metric has an explanation in `warnings`. Percentages are fractions × 100, rounded to 4 places, `ROUND_HALF_EVEN`. All arithmetic uses `Decimal`.

### Limitations

- Daily bars only. Orders fill at the open; intraday paths, gaps inside a day, partial fills, market impact beyond `slippage_bps`, and volume limits are not modeled.
- Long only: no short selling, margin, leverage, or interest on cash.
- Adjusted prices make returns total-return, but adjusted quantities and prices are not the literal historical share counts and quotes. Yahoo's adjustment factors can change after new dividends, so a later run of the same request can differ slightly.
- Indicators warm up inside the range, so a strategy cannot signal on the first `slow_window` (or `period`) days.
- Backtests run synchronously in the request. Very long ranges with many symbols take longer to fetch the first time; later runs use the market data cache.
- Past performance in a simulation does not predict future results.

## AI strategy analysis (Phase 3A.1)

Educational explanations of a stored backtest. Vektor measures the facts itself; an optional AI provider only interprets them. **Off by default:** with no provider configured the endpoint returns the measured facts and `"status": "unavailable"`, never a made-up analysis. Paper-only and educational: it describes a simulation and never gives investment advice, recommendations, forecasts, or promises of returns.

| Method and path (under `/api/v1`) | Does | Success |
|-----------------------------------|------|---------|
| `POST /backtests/{id}/analysis` | Measured facts about the stored backtest, plus an AI interpretation when a provider is configured | 200 `BacktestAnalysis` |

```bash
curl -X POST localhost:8000/api/v1/backtests/<id>/analysis
```

Contracts: `BacktestAnalysis`, `AnalysisFact`, `AnalysisInterpretation`, `AnalysisInsight` in `app/contracts.py`. The request has no body: only a stored backtest can be analyzed, so the numbers always come from a real simulation, never from the client. The analysis is generated on each request and not stored.

### Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `VEKTOR_AI_PROVIDER` | `none` | `none` (AI off) or `anthropic` (Claude through the official `anthropic` SDK) |
| `VEKTOR_AI_MODEL` | `claude-opus-5-5` | Model name sent to the provider |
| `VEKTOR_AI_API_KEY` | unset | Read from the environment only, held as a secret, never logged or returned. Unset: the SDK uses `ANTHROPIC_API_KEY` |
| `VEKTOR_AI_TIMEOUT_SECONDS` | `120` | Per-request timeout, more than 0 and at most 600. One retry for transient failures |

**Cost and scope:** `anthropic` calls a paid, hosted service billed to your Anthropic account, which goes beyond the free, local-first defaults in `AGENTS.md`. Leave the provider at `none` to keep Vektor fully local. Nothing else in Vektor depends on it.

### Response

- `facts`: always present. Each has an `id`, a `label`, and an exact `value` computed locally from the stored backtest (formulas at the top of `app/analysis/facts.py`): strategy and parameters, symbols, period, position size, costs, every metric (`unavailable` when null), the max drawdown's peak, trough and recovery dates, the longest drawdown in trading days, time in market, fills and closed trades, average, best and worst closed-trade return (realized P&L / buy notional plus buy fee), average holding period, fees as a share of starting cash, rejected orders, and positions left open.
- `interpretation`: the AI's reading, `null` when unavailable. `summary` plus `strategy_behavior`, `strengths`, `weaknesses`, `risk_factors` and `limitations`, each a list of insights. Every insight cites the fact ids it relies on in `evidence`; a reply that cites an id Vektor did not measure is rejected as a whole.
- `status` / `unavailable_reason`, `provider`, `model`, `generated_at`, `mode` (`paper`), and a fixed `disclaimer`.

Facts are measurement; `interpretation` is the model's explanation of them and can be wrong. Clients should present the two separately.

### What is sent to the provider

Only fixed instructions and a JSON list of the facts above with the backtest's metric notes. No backtest id, timestamps, raw trades, or account dollar amounts (starting cash, equity, P&L) leave the machine; the only dollar figure is the configured fee per fill. The instructions tell the model to use only those facts, cite them, copy numbers exactly, separate measurement from interpretation, and give no advice. The reply is constrained to the `AnalysisInterpretation` schema (structured output) and validated again by Vektor.

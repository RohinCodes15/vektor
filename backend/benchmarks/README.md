# Benchmarks (Phase 4B)

`bench.py` times the expensive API workloads end to end through the HTTP stack: validation, simulation, storage, and serialization. Each run uses a fresh temporary database. It works offline: a seeded random-walk provider stands in for Yahoo Finance, so every run computes the same prices and results.

```bash
cd backend
uv run python benchmarks/bench.py              # median and min of 5 runs, response sizes, result fingerprints
uv run python benchmarks/bench.py --repeat 7   # more runs per workload
uv run python benchmarks/bench.py --memory     # peak Python allocation per request (tracemalloc)
```

The **fingerprint** is a SHA-256 of the response JSON with ids and timestamps removed. If an optimization changes any price, fill, metric, curve point, or ranking, the fingerprint changes. The fingerprints below are identical before and after Phase 4B. Workloads that use a new symbol or add a stored backtest on every run (`history_uncached_20y`, `list_backtests_50`, `backtest_cold_5sym_10y_latency`) fingerprint their last run, so compare them at the same `--repeat`: the table uses 7.

## Workloads

| Workload | What it does |
|---|---|
| `history_uncached_20y` | `GET /market/history`, 20 years (about 5,200 bars), a new symbol each run: provider fetch plus cache write |
| `history_cached_20y` | The same request served from the SQLite cache |
| `backtest_3sym_20y_sma` | `POST /backtests`, 3 symbols, 20 years, SMA 20/50 with fees and slippage, stored |
| `comparison_5_strategies_20y` | `POST /backtests/comparisons`: buy and hold, 2 SMA and 2 RSI strategies, 20 years |
| `optimization_sma_100_20y` | `POST /backtests/optimizations`: 10 x 10 SMA grid (100 candidates), 20 years |
| `optimization_rsi_100_20y` | 4 periods x 5 oversold x 5 overbought RSI grid (100 candidates), 20 years |
| `list_backtests_50` | `GET /backtests` with about 57 stored 20-year backtests |
| `get_backtest_20y` | `GET /backtests/{id}` of one stored 20-year backtest |
| `backtest_cold_5sym_10y_latency` | `POST /backtests`, 5 uncached symbols, provider with 250 ms simulated latency per fetch |

## Results

Apple M3, Python 3.13, 7 runs per workload (`--repeat 7`). "Before" is commit `f1eee44` (end of Phase 4A), measured with this same script. Wire bytes are what is sent to a client that accepts gzip, as browsers do.

| Workload | Before median ms | After median ms | Change | Before wire bytes | After wire bytes | Fingerprint (both) |
|---|---:|---:|---|---:|---:|---|
| history_uncached_20y | 50.2 | 56.5 | +6 ms (gzip) | 643,223 | 175,770 | `ec77a494e3308ad1` |
| history_cached_20y | 26.0 | 33.5 | +7 ms (gzip) | 646,402 | 179,809 | `b84ee82a31de4b36` |
| backtest_3sym_20y_sma | 323.7 | 327.0 | same | 659,011 | 127,118 | `4d1672d750d93f11` |
| comparison_5_strategies_20y | 292.9 | 266.9 | 1.1x faster | 379,994 | 101,480 | `68e9c63a903eafb9` |
| optimization_sma_100_20y | 2812.9 | 1912.0 | 1.5x faster | 596,120 | 72,966 | `c4319ff39721b591` |
| optimization_rsi_100_20y | 2918.6 | 1732.0 | 1.7x faster | 594,520 | 103,024 | `f58602ea9d0c14af` |
| list_backtests_50 | 668.2 | 12.7 | 53x faster | 39,673 | 2,664 | `04d93bd398b8c906` |
| get_backtest_20y | 19.4 | 23.4 | +4 ms (gzip) | 659,011 | 127,117 | `4d1672d750d93f11` |
| backtest_cold_5sym_10y_latency | 1746.7 | 980.2 | 1.8x faster | 299,594 | 57,866 | `e94d84bef4ac8d9f` |

Portfolio valuation with 5 holdings on a cold cache and 250 ms provider latency, measured on the services by advancing the clock a day per run so every quote is uncached: median **1,292 ms before, 518 ms after**. Uncached quotes are now fetched concurrently. `tests/test_portfolio_service.py` covers the concurrency and the error order.

Gzip adds a few milliseconds of CPU per large response and cuts its size by 72 to 88%. On any real network link, sending 500 KB less saves far more than 5 ms. Level 1 was chosen by measurement on a 650 KB history:

| gzip level | Time | Size |
|---:|---:|---:|
| 1 | 4.5 ms | 179,811 |
| 5 | 13.2 ms | 153,833 |
| 9 (Starlette default) | 49.6 ms | 146,979 |

Peak Python memory per request (`--memory`):

| Workload | Before MiB | After MiB | Why |
|---|---:|---:|---|
| list_backtests_50 | 41.1 | 0.7 | Summaries are read from their own column instead of parsing every full result |
| optimization_sma_100_20y | 10.3 | 19.6 | Shared indicator series: at most one per distinct window, bounded by the 20-value grid limit |
| optimization_rsi_100_20y | 10.5 | 12.7 | Same, one RSI series per period |
| backtest_3sym_20y_sma | 19.0 | 22.2 | All symbols' histories are loaded together, so uncached ones can be fetched concurrently |
| comparison_5_strategies_20y | 9.6 | 11.8 | Shared indicator series |
| history and get workloads | 7.2 to 8.7 | 7.2 to 8.7 | Unchanged |

## SQLite: indexes and connections

Checked with `EXPLAIN QUERY PLAN` on every hot query:
- **Market data cache:** the entry lookup uses `history_fetches_lookup`, and the bar range read uses the `(fetch_id, date)` primary key. The pruning `DELETE` scans `history_fetches`, which holds one row per cached fetch, is pruned by the TTL, and is touched only on cache writes.
- **Backtests:** `get` uses the unique index on `id`. The listing scans every row, as it must; the summary column is what made it cheap.
- **Portfolios:** snapshots, transactions, order lookups and positions are all served by indexes or the primary key. Transactions sort per portfolio in a small temporary B-tree.

Opening a connection and running the idempotent schema script costs 0.11 to 0.17 ms. The fastest measured request takes 12 ms, so pooling would add shared state across threads for no measurable gain.

No index or connection change was justified, so none was made. The one storage change, the summary column, removed 98% of the listing's time.

## Where the time goes now

Profiled with `cProfile` on `BacktestService.optimize` (SMA grid):
- About 50% in the simulation loop (`Decimal` cash and position marking for each bar of each candidate).
- About 40% in `compute_performance` (daily returns, standard deviation, drawdowns, all in exact `Decimal`).
- Indicator computation dropped from about 25% to under 3% once each series was computed once.

What remains is inherent to exact decimal accounting on every bar of every candidate. Making it faster would need float arithmetic or vectorization, which would change rounding, so it is out of scope.

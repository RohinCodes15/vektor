# Vektor

**A local-first, paper-only workspace for researching trading strategies with real historical market data.**

Vektor combines simulated USD portfolios, historical backtests, strategy comparison, and parameter optimization in a dark research dashboard. It keeps financial calculations on a Python backend and presents the results through a typed Next.js frontend. Optional AI explanations interpret measured backtest facts; they do not calculate balances or place orders.

**Educational simulation only.** No brokerage connection, live execution, or real-money trading exists. Historical prices are real; cash, positions, fills, and performance are simulated. Past results do not predict returns, and AI output is not investment advice.

[Quick start](#quick-start) · [Architecture](#architecture) · [API](#api-and-documentation) · [Deployment](#deployment) · [Engineering](#engineering-decisions) · [Portfolio summary](PORTFOLIO.md)

## Features

| Workflow | Implemented behavior |
|---|---|
| Historical market research | On-demand daily OHLCV from Yahoo Finance through `yfinance`, validated and cached in SQLite. Interactive close-price charts preserve missing dates. No live quotes or generated prices. |
| Paper portfolios | API-based portfolio management and idempotent buy/sell orders with virtual USD. The dashboard displays holdings, cash, realized/unrealized P&L, and transaction history. Portfolio creation and order entry are available through the API, not dedicated dashboard forms. |
| Portfolio analytics | Recorded equity snapshots, returns, annualized volatility, Sharpe ratio, and drawdown. Allocation, concentration, risk contributions, and correlations describe current holdings. Insufficient history and unavailable prices remain explicit. |
| Strategy backtesting | Buy & Hold, SMA crossover, and Wilder's RSI; configurable capital, fees, and slippage. Equity/drawdown charts, performance metrics, and sortable simulated trades. The API supports multiple symbols; the current backtest form accepts one ticker. |
| AI strategy insights | Optional on-demand summaries, behavior, strengths, weaknesses, risks, and limitations, citing locally measured facts. AI-off responses still include facts and report interpretation as unavailable. |
| Strategy comparison | Compare 2–5 distinct configurations on one ticker with shared settings. Interactive equity curves, side-by-side metrics, baseline differences in the API, and backend-reported metric leaders. |
| Parameter optimization | Bounded SMA/RSI grid search with up to 100 valid combinations. Training-only ranking, a chronological holdout, ranked parameter results, separate train/test charts, and overfitting warning flags. |

The frontend includes keyboard chart exploration, responsive tables, focus states, reduced-motion support, and clear loading/error/empty states. Core workflows require no AI account. Fetching market data requires internet access; the app shell and local storage do not require a hosted service.

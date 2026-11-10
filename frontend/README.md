# Vektor frontend

A local-first, paper-only research dashboard built with Next.js App Router, React, TypeScript, Tailwind CSS v4, and Motion. It displays real historical market data and simulated portfolio/backtest results; it never routes orders to a broker.

The shell and optional guided demo render without a backend. Health checks and all portfolio, market-history, backtest, comparison, optimization, and AI-analysis requests require the FastAPI backend. Market data additionally depends on Yahoo Finance availability. An unavailable backend produces connection/error states, never sample financial data.


# AGENTS.md — Vektor

Vektor is a free, local-first, **paper-only** algorithmic trading simulator.

## Non-negotiables

- **Paper trading only.** No live trading, no brokerage integrations or credentials, no real-money execution, no paid services. `trading_mode` is the literal `"paper"`; any other value fails startup. Do not add broker SDKs, API-key settings, or order routing to external venues.
- **Local-first.** Runs on a developer machine with no accounts or network services required.
- **No secrets in the repo.** `.env` is git-ignored; only `.env.example` is committed.

## Ownership

| Area | Owner | Rule |
|------|-------|------|
| `backend/` | Claude | Only Claude edits it. |
| `frontend/` | Codex | Only Codex edits it. |
| Shared contracts: `backend/app/contracts.py` and the `/api/v1` surface | Both | Coordinated. Neither agent changes them alone: propose the change, get agreement, then update backend and frontend together. |
| Root files (`AGENTS.md`, `.gitignore`) | Both | Coordinated. |

If a task needs a change in an area you don't own, stop and hand it off. Don't edit it yourself.

## Architecture

```
backend/                  Python 3.12+, FastAPI, managed with uv
  app/main.py             create_app(): logging, CORS, error handlers, /api/v1 router, /api/v1/health
  app/config.py           Settings (pydantic-settings, VEKTOR_* env vars / backend/.env)
  app/contracts.py        Shared Pydantic request/response models (the API contract)
  app/api_errors.py       Every API error is an ErrorResponse {"detail": str}
  app/validation.py       Readable, input-free summaries of validation errors
  app/logging_config.py   JSON-lines logging (stdlib)
  app/routers/market.py   GET /api/v1/market/history (read-only)
  app/market_data/        Historical OHLCV: yfinance provider, normalization, SQLite cache, service
  tests/                  pytest (provider mocked; no network)
frontend/                 Owned by Codex (not yet created)
```

- The API is versioned under `/api/v1`. Breaking changes go into a new version prefix, never into an existing one.
- Contracts are Pydantic models with `extra="forbid"` and `frozen=True`. Validation happens at the boundary through field constraints.
- `Simulation`, `SimulationCreate` and `PaperOrder` are contracts only. No endpoints serve them yet.
- Market data is read-only daily history from Yahoo Finance (free, no API key). It is never fabricated, filled, or repaired: invalid provider data is rejected with an error.

## Engineering standards

- Type annotations on every function. Immutable data where practical.
- Add a module only when there is code to put in it. Split `main.py` into routers or services once real features arrive, not before.
- Every behavior change ships with a pytest test. `uv run pytest` must pass before handing off.
- Log with `logging` (JSON output). Never log secrets. Don't use `print`.
- Never add a dependency for a few lines of code. Pin new dependencies in `pyproject.toml` and commit `uv.lock`.
- Conventional commits (`feat:`, `fix:`, `chore:` …).

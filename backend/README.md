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

All settings are `VEKTOR_*` environment variables or keys in `backend/.env` (see `.env.example`). Unknown keys in `.env` are rejected. `VEKTOR_TRADING_MODE` only accepts `paper`.

# Launch readiness (Phase 5E)

Final verification before the first deployment, run on 2026-11-09 against commit `1969915` plus the Phase 5E fixes
below. Nothing was deployed and no paid resource was created. Every result here was observed in this run.

**Verdict: ready to deploy.** Every critical check passes. What remains are operator steps (an account, a domain, a
volume), not code defects. See "Before the first deploy".

## Checks

| Area | Check | Result |
|---|---|---|
| Backend tests | `uv run pytest` | PASS: 740 passed (727 before Phase 5E, plus 13 new) |
| Backend lint | `uvx ruff check .` (rules pinned in `pyproject.toml`) | PASS |
| Frontend | `npm run typecheck`, `npm run lint` | PASS |
| Frontend | `npm test` | PASS: 143 passed |
| Frontend | `NEXT_PUBLIC_API_ORIGIN=https://… npm run build` | PASS (static `/`) |
| Workflows, real Yahoo data | Market history, paper orders, analytics, backtests, AI insights (provider off), comparison, optimization | PASS: 32/32 |
| Security probes | Paper-only settings, CORS, headers, body and rate limits, safe errors, request ids | PASS: 21/21 |
| Production server | Real uvicorn in production mode, with temporary databases | PASS |
| Docker image | Built and run with a volume (colima) | PASS |
| Browser | Frontend dev server plus backend, in Chromium | PASS, with the notes below |


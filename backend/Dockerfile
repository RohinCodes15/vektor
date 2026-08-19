# syntax=docker/dockerfile:1
# Vektor backend: paper-only FastAPI service. One process; SQLite lives on the volume mounted at /data.
FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    XDG_CACHE_HOME=/tmp/cache \
    PORT=8000 \
    VEKTOR_ENVIRONMENT=production
WORKDIR /app
# Dependencies first, from the lockfile only, so code changes reuse this layer. No dev dependencies.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN useradd --system --uid 10001 --user-group --home-dir /app --no-create-home vektor \
    && mkdir -p /data && chown vektor:vektor /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/v1/health\", timeout=4)"]
# The entrypoint makes /data writable by the unprivileged `vektor` user, then drops root.
# One worker: rate limits and the expensive-request cap are per process, and SQLite expects a single writer.
# uvicorn reads FORWARDED_ALLOW_IPS from the environment to trust the platform proxy's X-Forwarded-For.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --workers 1 --proxy-headers --no-server-header --no-access-log"]

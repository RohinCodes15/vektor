import asyncio
import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message

from app.middleware import (
    RateLimit,
    RequestBodyLimit,
    is_expensive,
)


def echo_app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/v1/backtests")
    async def expensive(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/api/v1/backtests", True),
        ("POST", "/api/v1/backtests/comparisons", True),
        ("POST", "/api/v1/backtests/optimizations", True),
        ("POST", "/api/v1/backtests/3f1c/analysis", True),
        ("GET", "/api/v1/backtests", False),
        ("GET", "/api/v1/backtests/3f1c", False),
        ("POST", "/api/v1/portfolios", False),
        ("POST", "/api/v1/backtestsx", False),
    ],
)
def test_expensive_requests_are_every_post_under_backtests(method: str, path: str, expected: bool) -> None:
    assert is_expensive({"method": method, "path": path}) is expected


# --- request body limit ------------------------------------------------------------------------------------------


def body_client(limit: int = 1024) -> TestClient:
    app = echo_app()
    app.add_middleware(RequestBodyLimit, max_bytes=limit)
    return TestClient(app)


def test_a_body_within_the_limit_passes() -> None:
    res = body_client().post("/api/v1/backtests", content=b"x" * 1024)
    assert res.status_code == 200 and res.json() == {"bytes": 1024}


def test_a_declared_oversize_body_is_rejected_before_the_app_reads_it() -> None:
    res = body_client().post("/api/v1/backtests", content=b"x" * 1025)
    assert res.status_code == 413
    assert res.json() == {"detail": "Request body is larger than the 1024-byte limit."}


def test_a_streamed_oversize_body_without_content_length_is_rejected() -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(4):
            yield b"x" * 400

    res = body_client().post("/api/v1/backtests", content=chunks())
    assert res.status_code == 413 and "1024-byte limit" in res.json()["detail"]


def test_a_malformed_content_length_is_a_bad_request() -> None:
    async def run() -> list[Message]:
        sent: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": "/", "headers": [(b"content-length", b"-5")]}
        await RequestBodyLimit(echo_app(), 1024)(scope, receive, send)
        return sent

    sent = asyncio.run(run())
    assert sent[0]["status"] == 400
    assert json.loads(sent[1]["body"]) == {"detail": "Content-Length must be a whole number of bytes."}


# --- rate limit --------------------------------------------------------------------------------------------------


def test_rate_limit_counts_per_client_and_bucket_and_resets_each_minute() -> None:
    clock = Clock()
    limiter = RateLimit(echo_app(), per_minute=3, expensive_per_minute=1, clock=clock)
    assert [limiter._hit("a", "general") for _ in range(3)] == [None, None, None]
    assert limiter._hit("a", "general") == 60
    assert limiter._hit("b", "general") is None  # another client has its own window
    assert limiter._hit("a", "expensive") is None  # and so does the stricter bucket
    clock.now += 45
    assert limiter._hit("a", "expensive") == 15
    clock.now += 15
    assert limiter._hit("a", "general") is None and limiter._hit("a", "expensive") is None


def test_a_zero_limit_disables_its_bucket() -> None:
    limiter = RateLimit(echo_app(), per_minute=0, expensive_per_minute=0)
    assert all(limiter._hit("a", bucket) is None for bucket in ("general", "expensive") for _ in range(1000))


def test_stale_windows_are_swept_so_memory_stays_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.middleware.MAX_TRACKED_KEYS", 3)
    clock = Clock()
    limiter = RateLimit(echo_app(), per_minute=5, expensive_per_minute=5, clock=clock)
    for client in ("a", "b", "c"):
        limiter._hit(client, "general")
    clock.now += 61
    limiter._hit("d", "general")
    assert set(limiter.windows) == {("d", "general")}


def test_over_the_limit_the_api_answers_429_with_retry_after() -> None:
    app = echo_app()
    app.add_middleware(RateLimit, per_minute=2, expensive_per_minute=1)
    client = TestClient(app)
    assert client.post("/api/v1/backtests", content=b"{}").status_code == 200
    res = client.post("/api/v1/backtests", content=b"{}")
    assert res.status_code == 429 and int(res.headers["retry-after"]) >= 1
    assert res.json()["detail"].startswith("Too many requests. Try again in")
    assert [client.get("/api/v1/health").status_code for _ in range(3)] == [200, 200, 429]

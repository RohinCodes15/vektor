import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.middleware import (
    ExpensiveConcurrencyLimit,
    OwnerOnly,
    RateLimit,
    RequestBodyLimit,
    RequestLogging,
    SecurityHeaders,
    client_ip,
    is_expensive,
    is_owner_only,
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


def forwarded_scope(*values: str) -> Scope:
    return {"client": ("10.0.0.9", 443), "headers": [(b"x-forwarded-for", v.encode()) for v in values]}


def test_without_trusted_proxies_the_client_is_the_tcp_peer_whatever_the_headers_say() -> None:
    assert client_ip(forwarded_scope("203.0.113.7")) == "10.0.0.9"
    assert client_ip({"headers": []}) == "unknown"


@pytest.mark.parametrize(
    ("values", "hops", "expected"),
    [
        (("203.0.113.7",), 1, "203.0.113.7"),
        (("1.1.1.1, 203.0.113.7",), 1, "203.0.113.7"),  # the left entry was written by the client
        (("1.1.1.1", "203.0.113.7"), 1, "203.0.113.7"),  # repeated headers are one list, in order
        (("1.1.1.1, 203.0.113.7, 10.1.1.1",), 2, "203.0.113.7"),
        ((" 2001:db8::1 ",), 1, "2001:db8::1"),
        ((), 1, "10.0.0.9"),  # did not come through the proxy: fall back to the peer
        (("203.0.113.7",), 2, "10.0.0.9"),  # fewer entries than trusted proxies
        (("1.1.1.1, not-an-ip",), 1, "10.0.0.9"),
    ],
)
def test_with_trusted_proxies_the_client_is_the_entry_the_outermost_proxy_appended(
    values: tuple[str, ...], hops: int, expected: str
) -> None:
    assert client_ip(forwarded_scope(*values), hops) == expected


def test_a_client_cannot_dodge_the_rate_limit_by_inventing_forwarded_addresses() -> None:
    app = echo_app()
    app.add_middleware(RateLimit, per_minute=2, expensive_per_minute=1, trusted_proxy_hops=1)
    client = TestClient(app)
    codes = [
        client.get("/api/v1/health", headers={"x-forwarded-for": f"198.51.100.{n}, 203.0.113.7"}).status_code
        for n in range(3)
    ]
    assert codes == [200, 200, 429]
    other = client.get("/api/v1/health", headers={"x-forwarded-for": "203.0.113.8"})
    assert other.status_code == 200  # a different real client keeps its own window


# --- owner-only requests (public mode) ---------------------------------------------------------------------------

OWNER_KEY = "k" * 40


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/api/v1/portfolios", True),
        ("PATCH", "/api/v1/portfolios/3f1c", True),
        ("DELETE", "/api/v1/portfolios/3f1c", True),
        ("POST", "/api/v1/portfolios/3f1c/orders", True),
        ("POST", "/api/v1/portfolios/3f1c/snapshots", True),
        ("GET", "/api/v1/backtests", True),
        ("GET", "/api/v1/backtests/", True),
        ("GET", "/api/v1/portfolios", False),
        ("GET", "/api/v1/portfolios/3f1c/holdings", False),
        ("POST", "/api/v1/backtests", False),
        ("POST", "/api/v1/backtests/comparisons", False),
        ("GET", "/api/v1/backtests/3f1c", False),
        ("POST", "/api/v1/backtests/3f1c/analysis", False),
        ("OPTIONS", "/api/v1/portfolios", False),
    ],
)
def test_owner_only_requests_are_portfolio_writes_and_the_backtest_listing(
    method: str, path: str, expected: bool
) -> None:
    assert is_owner_only({"method": method, "path": path}) is expected


def owner_app(enabled: bool, owner_key: str | None) -> TestClient:
    app = FastAPI()

    @app.post("/api/v1/portfolios")
    def create() -> dict[str, str]:
        return {"created": "yes"}

    @app.get("/api/v1/portfolios")
    def listing() -> list[str]:
        return []

    app.add_middleware(OwnerOnly, enabled=enabled, owner_key=owner_key)
    return TestClient(app)


def test_public_mode_turns_away_portfolio_writes_without_the_owner_key(caplog: pytest.LogCaptureFixture) -> None:
    client = owner_app(enabled=True, owner_key=OWNER_KEY)
    for headers in ({}, {"x-vektor-owner-key": "wrong"}, {"x-vektor-owner-key": OWNER_KEY[:-1]}):
        res = client.post("/api/v1/portfolios", headers=headers)
        assert res.status_code == 403 and res.json()["detail"].startswith("This public deployment is read-only")
    assert client.get("/api/v1/portfolios").status_code == 200  # reading is still open
    assert OWNER_KEY not in caplog.text and "wrong" not in caplog.text


def test_the_owner_key_unlocks_owner_only_requests() -> None:
    client = owner_app(enabled=True, owner_key=OWNER_KEY)
    assert client.post("/api/v1/portfolios", headers={"x-vektor-owner-key": OWNER_KEY}).status_code == 200


def test_public_mode_without_an_owner_key_allows_no_writes_at_all() -> None:
    client = owner_app(enabled=True, owner_key=None)
    assert client.post("/api/v1/portfolios", headers={"x-vektor-owner-key": ""}).status_code == 403


def test_outside_public_mode_writes_need_no_key() -> None:
    assert owner_app(enabled=False, owner_key=None).post("/api/v1/portfolios").status_code == 200


# --- expensive concurrency limit ---------------------------------------------------------------------------------


def test_expensive_requests_beyond_the_concurrency_limit_are_turned_away() -> None:
    async def run() -> tuple[list[int], int]:
        release = asyncio.Event()
        started = 0

        async def slow_app(scope: Scope, receive: Receive, send: Send) -> None:
            nonlocal started
            started += 1
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        limiter = ExpensiveConcurrencyLimit(slow_app, max_concurrent=2)

        async def call(method: str = "POST") -> int:
            statuses: list[int] = []

            async def receive() -> Message:
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    statuses.append(message["status"])

            await limiter({"type": "http", "method": method, "path": "/api/v1/backtests", "headers": []},
                          receive, send)
            return statuses[0]

        running = [asyncio.create_task(call()) for _ in range(2)]
        await asyncio.sleep(0)
        rejected = await call()
        cheap = asyncio.create_task(call("GET"))  # not expensive: never counted or blocked
        await asyncio.sleep(0)
        release.set()
        statuses = [await task for task in running] + [rejected, await cheap]
        after = await call()  # slots are released afterwards
        return statuses, after if limiter.in_flight == 0 else -1

    statuses, after = asyncio.run(run())
    assert statuses == [200, 200, 503, 200] and after == 200


def test_the_busy_response_is_a_safe_error_with_retry_after() -> None:
    async def run() -> list[Message]:
        sent: list[Message] = []
        limiter = ExpensiveConcurrencyLimit(echo_app(), max_concurrent=1)
        limiter.in_flight = 1

        async def receive() -> Message:
            return {"type": "http.request", "body": b""}

        async def send(message: Message) -> None:
            sent.append(message)

        await limiter({"type": "http", "method": "POST", "path": "/api/v1/backtests", "headers": []}, receive, send)
        return sent

    start, body = asyncio.run(run())
    assert start["status"] == 503 and (b"retry-after", b"5") in start["headers"]
    assert json.loads(body["body"]) == {"detail": "The server is busy with other backtests. Try again shortly."}


# --- security headers ----------------------------------------------------------------------------------------------


def headers_client(hsts: bool) -> TestClient:
    app = echo_app()
    app.add_middleware(SecurityHeaders, hsts=hsts)
    return TestClient(app)


def test_security_headers_are_added_to_api_responses() -> None:
    headers = headers_client(hsts=False).get("/api/v1/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
    assert headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "strict-transport-security" not in headers


def test_hsts_is_sent_when_enabled_and_docs_keep_their_scripts() -> None:
    client = headers_client(hsts=True)
    assert client.get("/api/v1/health").headers["strict-transport-security"].startswith("max-age=31536000")
    docs = client.get("/docs")
    assert docs.status_code == 200 and "content-security-policy" not in docs.headers


# --- request logging -----------------------------------------------------------------------------------------------


def logged_client() -> TestClient:
    app = echo_app()
    app.add_middleware(RequestLogging)
    return TestClient(app)


def http_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "vektor.http"]


def test_each_request_is_logged_with_an_id_but_no_query_or_body(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="vektor.http")
    res = logged_client().post(
        "/api/v1/backtests?token=sk-ant-query-secret", content=b'{"key":"sk-ant-body-secret"}',
        headers={"authorization": "Bearer sk-ant-header-secret"},
    )
    (record,) = http_records(caplog)
    fields: dict[str, Any] = vars(record)
    assert fields["request_id"] == res.headers["x-request-id"] and len(fields["request_id"]) == 32
    assert (fields["method"], fields["path"], fields["status"]) == ("POST", "/api/v1/backtests", 200)
    assert isinstance(fields["duration_ms"], float)
    rendered = json.dumps(fields, default=str)
    assert "sk-ant" not in rendered and "token" not in rendered


def test_a_safe_incoming_request_id_is_kept_and_an_unsafe_one_replaced(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="vektor.http")
    client = logged_client()
    assert client.get("/api/v1/health", headers={"x-request-id": "trace-123.a_b"}).headers["x-request-id"] == (
        "trace-123.a_b"
    )
    replaced = client.get("/api/v1/health", headers={"x-request-id": "bad id\n{json}"}).headers["x-request-id"]
    assert replaced != "bad id\n{json}" and len(replaced) == 32
    assert [record.request_id for record in http_records(caplog)] == ["trace-123.a_b", replaced]  # type: ignore[attr-defined]


def test_a_request_that_crashes_is_still_logged_as_a_500(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="vektor.http")
    app = FastAPI()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("internal detail")

    app.add_middleware(RequestLogging)
    assert TestClient(app, raise_server_exceptions=False).get("/boom").status_code == 500
    (record,) = http_records(caplog)
    assert record.status == 500  # type: ignore[attr-defined]

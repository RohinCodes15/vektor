"""HTTP hardening as pure ASGI middleware: no dependencies, in-process state only (one server process).

- RequestBodyLimit: 413 for a body over the limit, whether declared by Content-Length or streamed.
- RateLimit: fixed one-minute windows per client IP, with a stricter bucket for expensive requests; 429 + Retry-After.
- ExpensiveConcurrencyLimit: at most N expensive requests run at once across all clients; 503 + Retry-After.
- SecurityHeaders: nosniff, no framing, no referrer, no caching, a deny-all CSP for API responses, HSTS in production.
- UnexpectedErrors: an unhandled exception becomes the generic 500 inside this stack, so it still gets CORS, security
  headers and the request id. Starlette would otherwise answer it from its outermost middleware, outside all of these.
- RequestLogging: one JSON line per request (request id, method, path, status, duration). Never the query string,
  headers, or body, so no credentials or payloads reach the logs.

Behind reverse proxies, set trusted_proxy_hops (VEKTOR_TRUSTED_PROXY_HOPS) to how many of them append to
X-Forwarded-For. The rate limit then keys on the entry the outermost trusted proxy added, never on entries to its left,
which the client wrote itself. uvicorn's --forwarded-allow-ips "*" uses the leftmost entry, so a client could pick a new
IP for every request.
"""

import ipaddress
import logging
import math
import re
import time
from collections.abc import Callable
from uuid import uuid4

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.contracts import ErrorResponse

logger = logging.getLogger("vektor.http")
error_logger = logging.getLogger("vektor")
INTERNAL_ERROR = "Internal server error"

WINDOW_SECONDS = 60
# Stale rate-limit windows are swept once this many clients are tracked, which bounds memory.
MAX_TRACKED_KEYS = 10_000
CONCURRENCY_RETRY_AFTER_SECONDS = 5
REQUEST_ID_HEADER = b"x-request-id"
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
# Swagger UI and ReDoc load scripts and styles, so the deny-all CSP would break them.
DOCS_PATHS = ("/docs", "/redoc")


def is_expensive(scope: Scope) -> bool:
    """Backtests, comparisons, optimizations, and AI analysis: every POST under /api/v1/backtests."""
    path: str = scope["path"]
    return scope["method"] == "POST" and (path == "/api/v1/backtests" or path.startswith("/api/v1/backtests/"))


def client_ip(scope: Scope, trusted_proxy_hops: int = 0) -> str:
    """The TCP peer, or with N trusted proxies the Nth X-Forwarded-For entry from the right when it is a valid IP."""
    if trusted_proxy_hops:
        forwarded = [
            entry.strip()
            for name, value in scope["headers"]
            if name == b"x-forwarded-for"
            for entry in value.decode("latin-1").split(",")
        ]
        if len(forwarded) >= trusted_proxy_hops:
            try:
                return str(ipaddress.ip_address(forwarded[-trusted_proxy_hops]))
            except ValueError:
                pass
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


async def send_error(send: Send, status: int, detail: str, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = ErrorResponse(detail=detail).model_dump_json().encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            *(headers or []),
        ],
    })
    await send({"type": "http.response.body", "body": body})


class RequestBodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            if not declared.isdigit():
                await send_error(send, 400, "Content-Length must be a whole number of bytes.")
                return
            if int(declared) > self.max_bytes:
                await send_error(send, 413, self._message())
                return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:  # a chunked body without Content-Length
                    raise HTTPException(413, self._message())
            return message

        await self.app(scope, limited_receive, send)

    def _message(self) -> str:
        return f"Request body is larger than the {self.max_bytes}-byte limit."


class RateLimit:
    def __init__(
        self,
        app: ASGIApp,
        per_minute: int,
        expensive_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        trusted_proxy_hops: int = 0,
    ) -> None:
        self.app = app
        self.limits = {"general": per_minute, "expensive": expensive_per_minute}
        self.trusted_proxy_hops = trusted_proxy_hops
        self.clock = clock
        # (client ip, bucket) -> (window start, requests in the window). The event loop is single-threaded.
        self.windows: dict[tuple[str, str], tuple[float, int]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        bucket = "expensive" if is_expensive(scope) else "general"
        retry_after = self._hit(client_ip(scope, self.trusted_proxy_hops), bucket)
        if retry_after is not None:
            logger.warning("rate limit exceeded", extra={"bucket": bucket, "path": scope["path"]})
            await send_error(
                send,
                429,
                f"Too many requests. Try again in {retry_after} seconds.",
                [(b"retry-after", str(retry_after).encode())],
            )
            return
        await self.app(scope, receive, send)

    def _hit(self, client: str, bucket: str) -> int | None:
        """Count a request; the seconds until the window resets when it is over the limit, else None."""
        limit = self.limits[bucket]
        if limit == 0:
            return None
        now = self.clock()
        if len(self.windows) >= MAX_TRACKED_KEYS:
            self.windows = {k: v for k, v in self.windows.items() if now - v[0] < WINDOW_SECONDS}
        start, count = self.windows.get((client, bucket), (now, 0))
        if now - start >= WINDOW_SECONDS:
            start, count = now, 0
        if count >= limit:
            return max(1, math.ceil(start + WINDOW_SECONDS - now))
        self.windows[(client, bucket)] = (start, count + 1)
        return None


class ExpensiveConcurrencyLimit:
    def __init__(self, app: ASGIApp, max_concurrent: int) -> None:
        self.app = app
        self.max_concurrent = max_concurrent
        self.in_flight = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_expensive(scope):
            await self.app(scope, receive, send)
            return
        if self.in_flight >= self.max_concurrent:
            logger.warning("expensive request concurrency limit reached", extra={"path": scope["path"]})
            await send_error(
                send,
                503,
                "The server is busy with other backtests. Try again shortly.",
                [(b"retry-after", str(CONCURRENCY_RETRY_AFTER_SECONDS).encode())],
            )
            return
        self.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1


class UnexpectedErrors:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            # Logged server-side only; the client gets the generic message, never the exception's details.
            error_logger.error("unhandled error", extra={"path": scope["path"]}, exc_info=True)
            if started:  # too late for a clean error response: let the server abort the connection
                raise
            await send_error(send, 500, INTERNAL_ERROR)


class SecurityHeaders:
    def __init__(self, app: ASGIApp, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        docs = scope["path"].startswith(DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                wanted = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cross-origin-resource-policy", b"same-site"),
                    (b"cache-control", b"no-store"),
                ]
                if not docs:
                    wanted.append((b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"))
                if self.hsts:
                    wanted.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                headers += [(name, value) for name, value in wanted if name not in present]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestLogging:
    def __init__(self, app: ASGIApp, clock: Callable[[], float] = time.perf_counter) -> None:
        self.app = app
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER, b"").decode("latin-1")
        request_id = incoming if SAFE_REQUEST_ID.fullmatch(incoming) else uuid4().hex
        started = self.clock()
        status = 500  # if the app fails before responding, the error handler's 500 is what the client sees

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [(n, v) for n, v in message.get("headers", []) if n.lower() != REQUEST_ID_HEADER]
                message = {**message, "headers": [*headers, (REQUEST_ID_HEADER, request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((self.clock() - started) * 1000, 1),
                },
            )

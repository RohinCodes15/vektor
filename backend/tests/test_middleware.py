import asyncio
import json
from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message

from app.middleware import RequestBodyLimit


def echo_app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/v1/backtests")
    async def expensive(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


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

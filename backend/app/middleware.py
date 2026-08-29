"""HTTP hardening as pure ASGI middleware: no dependencies, in-process state only (one server process).

- RequestBodyLimit: 413 for a body over the limit, whether declared by Content-Length or streamed.
"""

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.contracts import ErrorResponse


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

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ReportBodyLimit:
    """Bound actual request bytes before JSON decoding, including chunked bodies."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].startswith("/api/v1/conversations/")
            or not scope["path"].endswith("/reports")
        ):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 128 * 1024:
                response = JSONResponse({"detail": {"code": "report_request_too_large"}}, 413)
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def buffered() -> Message:
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, buffered, send)

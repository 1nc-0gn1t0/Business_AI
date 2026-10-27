"""Bounded, allowlisted diagnostics. Never pass exceptions, payloads or URLs here."""

import asyncio
import json
import logging
import threading
import time
from collections import Counter, deque
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="operator")
LOGGER = logging.getLogger("business_ai.events")
OPERATIONS = {"api", "chat", "geo", "finance", "bank", "leads", "reports", "health", "other"}


def database_failure_code(error: Exception) -> str:
    return "database_capacity_busy" if isinstance(error, PoolTimeout) else "database_unavailable"


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # No record.getMessage()/exc_info: third-party records may contain credentials.
        return json.dumps(getattr(record, "safe_event", {"event": "external_log_suppressed"}))


def configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.getLogger().addHandler(logging.StreamHandler())
    for handler in logging.getLogger().handlers:
        handler.setFormatter(SafeFormatter())
    logging.getLogger().setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx2", "httpcore"):
        log = logging.getLogger(name)
        log.handlers = []
        log.propagate = True
    logging.getLogger("uvicorn.access").disabled = True


class Observations:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counts: Counter[str] = Counter()
        self.seconds: dict[str, float] = {}
        self.codes: Counter[str] = Counter()
        self.recent: deque[dict[str, object]] = deque(maxlen=32)

    def observe(self, operation: str, status: int, duration: float) -> None:
        key = f"{operation}:{status // 100}xx"
        with self.lock:
            self.counts[key] += 1
            self.seconds[key] = self.seconds.get(key, 0) + duration

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {
                "counts": dict(self.counts),
                "seconds_total": dict(self.seconds),
                "codes": dict(self.codes),
                "recent": list(self.recent),
            }


OBSERVATIONS = Observations()


def event(operation: str, status: int, duration: float, code: str = "ok") -> None:
    operation = operation if operation in OPERATIONS | {"inference", "queue"} else "other"
    # Codes come from server logic; enforce fixed syntax/length as defense in depth.
    code = (
        code if code.isascii() and code.replace("_", "").isalnum() and len(code) < 80 else "error"
    )
    OBSERVATIONS.observe(operation, status, duration)
    failed = status >= 500 or code in {"internal_error", "export_failed"}
    fields: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": "error" if failed else "warning" if status >= 400 else "info",
        "request_id": REQUEST_ID.get(),
        "operation": operation,
        "status": status,
        "duration_seconds": round(duration, 6),
        "code": code,
        "application_version": "0.1.0",
    }
    with OBSERVATIONS.lock:
        OBSERVATIONS.codes[
            code if code in OBSERVATIONS.codes or len(OBSERVATIONS.codes) < 64 else "other"
        ] += 1
        OBSERVATIONS.recent.append(fields)
    LOGGER.log(
        logging.ERROR if failed else logging.WARNING if status >= 400 else logging.INFO,
        "event",
        extra={"safe_event": fields},
    )


def category(path: str) -> str:
    if path in {"/healthz", "/livez", "/readyz"}:
        return "health"
    if not path.startswith("/api/v1/"):
        return "other"
    parts = path.split("/")
    for part, operation in (
        ("reports", "reports"),
        ("messages", "chat"),
        ("leads", "leads"),
        ("geo", "geo"),
        ("finance", "finance"),
        ("bank-products", "bank"),
    ):
        if part in parts:
            return operation
    return "api"


class Diagnostics:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex  # Never trust client-supplied IDs, including valid-looking ones.
        token = REQUEST_ID.set(request_id)
        started, status, sent = time.monotonic(), 500, False
        code, pending, body = "internal_error", None, bytearray()

        async def emit(message: Message) -> None:
            nonlocal status, sent, pending, code
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    (k, v) for k, v in message["headers"] if k.lower() != b"x-request-id"
                ] + [(b"x-request-id", request_id.encode())]
                if status >= 400:
                    pending = message
                    return
                sent = True
            if message["type"] == "http.response.body" and pending is not None:
                if len(body) + len(message.get("body", b"")) <= 65536:
                    body.extend(message.get("body", b""))
                if message.get("more_body", False):
                    return
                try:
                    payload = json.loads(body)
                    detail = payload.get("detail")
                    code = (
                        detail.get("code", f"http_{status}")
                        if isinstance(detail, dict)
                        else f"http_{status}"
                    )
                except (ValueError, AttributeError):
                    payload, code = {}, f"http_{status}"
                payload.update(
                    code=code,
                    message="Проверьте вводные или дождитесь восстановления сервиса.",
                    request_id=request_id,
                )
                response = JSONResponse(payload, status)
                pending["headers"] = [
                    (k, v)
                    for k, v in pending["headers"]
                    if k.lower() not in {b"content-length", b"content-type"}
                ] + list(response.raw_headers)
                sent = True
                await send(pending)
                await send({"type": "http.response.body", "body": response.body})
                return
            await send(message)

        try:
            await self.app(scope, receive, emit)
            if status < 400:
                code = "ok"
        except asyncio.CancelledError:
            status, code = 499, "request_cancelled"
            raise
        except Exception:
            code = "export_failed" if category(scope["path"]) == "reports" else "internal_error"
            if not sent:
                pending, body, status = None, bytearray(), 500
                await JSONResponse({"detail": {"code": code}}, 500)(scope, receive, emit)
            # Do not let Uvicorn emit exception/SQL/traceback outside the safe boundary.
        finally:
            event(category(scope["path"]), status, time.monotonic() - started, code)
            REQUEST_ID.reset(token)

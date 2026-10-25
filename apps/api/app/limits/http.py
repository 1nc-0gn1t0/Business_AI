import asyncio
import json
import math
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.limits.config import Limits, policy


class Rejected(Exception):
    def __init__(self, code: str, status: int, retry: int | None = None):
        self.code, self.status, self.retry = code, status, retry


class Admission:
    """Fixed-size process-local counters, never keyed by attacker supplied IDs/IPs."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.since = clock()
        self.requests = self.heavy = self.active = self.active_heavy = 0

    def enter(self, heavy: bool, *, control: bool = False) -> None:
        cfg = policy()
        with self.lock:
            if self.active >= cfg.active_requests or (
                heavy and self.active_heavy >= cfg.active_heavy
            ):
                raise Rejected("request_capacity_busy", 429)
            if not control:
                self._charge(heavy)
            self.active += 1
            self.active_heavy += int(heavy)

    def _charge(self, heavy: bool) -> None:
        cfg, now = policy(), self.clock()
        if now - self.since >= cfg.window_seconds:
            self.since, self.requests, self.heavy = now, 0, 0
        if self.requests >= cfg.requests_per_window or (
            heavy and self.heavy >= cfg.heavy_per_window
        ):
            raise Rejected(
                "request_rate_limited",
                429,
                max(1, math.ceil(cfg.window_seconds - (now - self.since))),
            )
        self.requests += 1
        self.heavy += int(heavy)

    def charge(self, heavy: bool) -> None:
        with self.lock:
            self._charge(heavy)

    def leave(self, heavy: bool) -> None:
        with self.lock:
            self.active -= 1
            self.active_heavy -= int(heavy)


CONTROLLER = Admission()


def reset_admission() -> None:
    global CONTROLLER
    CONTROLLER = Admission()


def consent_control(path: str, method: str) -> bool:
    parts = path.strip("/").split("/")
    return (
        method == "GET"
        and (
            path == "/api/v1/consent-texts"
            or (
                len(parts) == 5
                and parts[:3] == ["api", "v1", "conversations"]
                and parts[-1] == "consents"
            )
        )
    ) or (
        method == "PUT"
        and len(parts) == 6
        and parts[:3] == ["api", "v1", "conversations"]
        and parts[-2] == "consents"
        and parts[-1] in {"assistant", "marketing", "demo_lead"}
    )


def heavy_request(path: str, method: str) -> bool:
    return (
        method == "POST"
        and (
            path.startswith(("/api/v1/geo/", "/api/v1/finance/"))
            or path.endswith(("/messages", "/reports"))
        )
    ) or (method == "GET" and "/reports/" in path)


def check_structure(body: bytes, cfg: Limits) -> None:
    if not body:
        return
    try:
        value = json.loads(body)
    except (ValueError, RecursionError):
        raise Rejected("invalid_request_structure", 422) from None
    if not isinstance(value, dict):
        raise Rejected("invalid_request_structure", 422)
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > cfg.json_nodes or depth > cfg.json_depth:
            raise Rejected("request_structure_too_large", 422)
        if isinstance(item, str) and len(item) > cfg.text_chars:
            raise Rejected("request_text_too_long", 422)
        if isinstance(item, float) and not math.isfinite(item):
            raise Rejected("invalid_request_structure", 422)
        if isinstance(item, (dict, list)):
            if len(item) > cfg.collection_items:
                raise Rejected("request_structure_too_large", 422)
            if isinstance(item, dict):
                if any(len(key) > 128 for key in item):
                    raise Rejected("request_structure_too_large", 422)
                values: Iterable[Any] = item.values()
            else:
                values = item
            stack.extend((child, depth + 1) for child in values)


class ApiLimits:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        cfg = policy()
        path, method = scope["path"].rstrip("/"), scope["method"]
        maximum = (
            cfg.report_body_bytes
            if method == "POST" and path.endswith("/reports")
            else cfg.body_bytes
        )
        size_code = (
            "report_request_too_large"
            if maximum == cfg.report_body_bytes and path.endswith("/reports")
            else "request_body_too_large"
        )
        controller, admitted = CONTROLLER, False
        heavy = heavy_request(path, method)
        try:
            if (
                len(scope["path"].encode("utf-8")) > cfg.path_bytes
                or len(scope.get("query_string", b"")) > cfg.query_bytes
            ):
                raise Rejected("request_target_too_large", 414)
            if sum(len(key) + len(value) for key, value in scope["headers"]) > cfg.header_bytes:
                raise Rejected("request_headers_too_large", 431)
            lengths = [value for key, value in scope["headers"] if key.lower() == b"content-length"]
            if lengths:
                if len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 20:
                    raise Rejected("invalid_request_structure", 422)
                if int(lengths[0]) > maximum:
                    raise Rejected(size_code, 413)
            control_route = consent_control(path, method)
            controller.enter(heavy, control=control_route)
            admitted = True
            body = bytearray()
            try:
                async with asyncio.timeout(cfg.body_timeout_seconds):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > maximum:
                            raise Rejected(size_code, 413)
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                raise Rejected("request_body_timeout", 408) from None
            if method in {"POST", "PUT", "PATCH"}:
                check_structure(bytes(body), cfg)
            if control_route:
                # Opt-out and its preview bypass time windows, not active-request caps.
                # Grants use the ordinary window; a different endpoint cannot evade it.
                control = method == "GET" or (
                    bool(body) and json.loads(body).get("decision") in ("withdraw", "decline")
                )
                if not control:
                    controller.charge(heavy)
            replayed = False

            async def buffered() -> Message:
                nonlocal replayed
                if replayed:
                    return await receive()
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, buffered, send)
        except Rejected as error:
            headers = {"Retry-After": str(error.retry)} if error.retry is not None else None
            await JSONResponse({"detail": {"code": error.code}}, error.status, headers=headers)(
                scope, receive, send
            )
        finally:
            if admitted:
                controller.leave(heavy)

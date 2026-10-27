import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.types import Message, Receive, Scope, Send

from app.db.session import get_session, get_session_factory
from app.diagnostics import Diagnostics, Observations, SafeFormatter, event
from app.main import app
from app.readiness import Readiness, ollama_probe

MARKER = "SYNTHETIC_SECRET_password_token_prompt"


@pytest.mark.parametrize("status", [400, 404, 409, 413, 422, 429, 502, 503, 504])
def test_safe_error_envelope_and_correlation(status: int, caplog: pytest.LogCaptureFixture) -> None:
    isolated = FastAPI()
    isolated.add_middleware(Diagnostics)

    @isolated.get("/fail")
    def fail() -> None:
        raise HTTPException(status, detail={"code": "controlled_failure"})

    with caplog.at_level(logging.INFO), TestClient(isolated) as client:
        response = client.get("/fail?secret=" + MARKER, headers={"X-Request-ID": MARKER})
    assert response.status_code == status
    result = response.json()
    assert result["detail"]["code"] == result["code"] == "controlled_failure"
    assert len(result["request_id"]) == 32
    assert response.headers["x-request-id"] == result["request_id"]
    records = [r.safe_event for r in caplog.records if hasattr(r, "safe_event")]
    assert records[-1]["request_id"] == result["request_id"]
    assert MARKER not in json.dumps(records) + response.text


@pytest.mark.parametrize("path", ["/api/v1/test", "/api/v1/conversations/fake/reports/file"])
def test_unexpected_and_export_exceptions_never_escape(path: str) -> None:
    isolated = FastAPI()
    isolated.add_middleware(Diagnostics)

    @isolated.get(path)
    def fail() -> None:
        raise RuntimeError(MARKER)

    with TestClient(isolated) as client:
        response = client.get(path)
    assert response.status_code == 500
    assert response.json()["code"] == ("export_failed" if "reports" in path else "internal_error")
    assert MARKER not in response.text


def test_liveness_does_not_probe_dependencies_and_readiness_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    async def probe() -> Readiness:
        calls.append(1)
        return Readiness(
            status="unavailable", database="unavailable", postgis="unknown", schema_status="unknown"
        )

    monkeypatch.setattr("app.main.database_probe", probe)
    with TestClient(app) as client:
        assert client.get("/livez").json() == {"status": "ok"}
        assert calls == []
        assert client.get("/readyz").status_code == 503

        async def healthy() -> Readiness:
            return Readiness(status="ok", database="ok", postgis="ok", schema_status="ok")

        monkeypatch.setattr("app.main.database_probe", healthy)
        assert client.get("/readyz").status_code == 200


def test_bundle_requires_real_separate_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def probe() -> dict[str, object]:
        calls.append(1)
        return {"bounded": True}

    monkeypatch.setattr("app.main.bundle", probe)
    monkeypatch.setenv("BA_DIAGNOSTICS_TOKEN", "x" * 32)
    with TestClient(app) as client:
        for headers in ({}, {"X-Diagnostics-Token": MARKER}):
            assert client.get("/api/v1/diagnostics", headers=headers).status_code == 404
        assert calls == []
        assert client.get(
            "/api/v1/diagnostics", headers={"X-Diagnostics-Token": "x" * 32}
        ).json() == {"bounded": True}
        monkeypatch.delenv("BA_DIAGNOSTICS_TOKEN")
        assert client.get("/api/v1/diagnostics").status_code == 404


@pytest.mark.parametrize("kind", ["present", "missing", "down", "timeout", "malformed", "oversize"])
def test_ollama_probe_bounded_no_generation(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    client_class = httpx2.AsyncClient

    async def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET" and request.url.path == "/api/tags"
        if kind == "down":
            raise httpx2.ConnectError(MARKER)
        if kind == "timeout":
            raise httpx2.ReadTimeout(MARKER)
        data: Any = (
            {"models": [{"name": "qwen3:4b-instruct-2507-q4_K_M"}]}
            if kind == "present"
            else {"models": []}
        )
        raw = json.dumps(data).encode()
        if kind == "malformed":
            raw = MARKER.encode()
        if kind == "oversize":
            raw = b"x" * 65537

        # Streaming mocks must expose raw bytes just like the real adapter.
        class Bytes(httpx2.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                yield raw

        return httpx2.Response(200, stream=Bytes())

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(
        "app.readiness.httpx2.AsyncClient",
        lambda **kw: client_class(transport=httpx2.MockTransport(handler), **kw),
    )
    result = asyncio.run(ollama_probe())
    assert result["inference"] == "not_tested"
    assert result["model"] == (kind if kind in {"present", "missing"} else "unknown")
    assert MARKER not in json.dumps(result)


def test_log_formatter_never_formats_raw_exception_or_message() -> None:
    record = logging.LogRecord("third_party", logging.ERROR, "", 0, MARKER, (), None)
    record.exc_info = (RuntimeError, RuntimeError(MARKER), None)
    assert MARKER not in SafeFormatter().format(record)


def test_diagnostics_storage_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = Observations()
    monkeypatch.setattr("app.diagnostics.OBSERVATIONS", observations)
    for index in range(200):
        event("reports", 500, 0.01, f"error_{index}")
    snapshot = observations.snapshot()
    assert len(observations.recent) == 32
    assert len(observations.codes) <= 65
    assert snapshot["counts"] == {"reports:5xx": 200}


def test_sql_exception_does_not_expose_statement_or_parameters() -> None:
    isolated = FastAPI()
    isolated.add_middleware(Diagnostics)

    @isolated.post("/api/v1/test")
    def fail() -> None:
        raise OperationalError(MARKER, {"token": MARKER}, Exception(MARKER))

    with TestClient(isolated) as client:
        result = client.post("/api/v1/test", json={"synthetic": MARKER})
    assert result.status_code == 500
    assert MARKER not in result.text


def test_real_body_limit_is_correlated_without_database_or_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def forbidden() -> None:
        raise AssertionError("Rejected payload must never reach the database")

    app.dependency_overrides[get_session] = forbidden
    app.dependency_overrides[get_session_factory] = forbidden
    try:
        with caplog.at_level(logging.INFO), TestClient(app) as client:
            response = client.post(
                "/api/v1/conversations/00000000-0000-0000-0000-000000000000/messages",
                content=json.dumps({"content": MARKER + "x" * 70000}),
            )
        assert response.status_code == 413
        assert response.json()["code"] == "request_body_too_large"
        assert response.headers["x-request-id"] == response.json()["request_id"]
        assert MARKER not in response.text + caplog.text
    finally:
        app.dependency_overrides.pop(get_session)
        app.dependency_overrides.pop(get_session_factory)


def test_pool_exhaustion_has_safe_distinct_code() -> None:
    def unavailable() -> None:
        raise PoolTimeout(MARKER)

    app.dependency_overrides[get_session] = unavailable
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/conversations")
        assert response.status_code == 503
        assert response.json()["code"] == "database_capacity_busy"
        assert MARKER not in response.text
    finally:
        app.dependency_overrides.pop(get_session)


def test_failure_after_headers_keeps_actual_status_but_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    messages: list[Message] = []

    async def broken(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError(MARKER)

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    with caplog.at_level(logging.INFO):
        asyncio.run(Diagnostics(broken)({"type": "http", "path": "/test"}, receive, send))
    assert len(messages) == 1  # Cannot replace a response already started.
    record = [r.safe_event for r in caplog.records if hasattr(r, "safe_event")][-1]
    assert record["status"] == 200 and record["severity"] == "error"
    assert record["code"] == "internal_error"
    assert MARKER not in json.dumps(record)

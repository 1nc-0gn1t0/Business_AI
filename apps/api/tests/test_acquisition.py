"""Deterministic security tests; no public service requests."""

import io
import secrets
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.data.acquisition import network
from app.data.acquisition.schemas import AcquisitionError, AcquisitionRequest, Resources
from app.data.acquisition.service import validate
from app.data.acquisition.worker import ProcessLock
from app.data.registry import load_registry
from app.main import app


def request() -> AcquisitionRequest:
    return AcquisitionRequest.model_validate(
        {
            "territory": "ru-moscow",
            "aoi": {"west": 37.61, "south": 55.75, "east": 37.612, "north": 55.752},
            "idempotency_key": "unit-fixture",
        }
    )


@pytest.mark.parametrize("source", ["osm", "synthetic", "ghsl", "licensed"])
def test_default_sources_cannot_fetch(source: str) -> None:
    with pytest.raises(AcquisitionError, match="source_not_permitted"):
        validate(request().model_copy(update={"source_id": source}), load_registry())


def test_unknown_source_and_category() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        validate(request().model_copy(update={"source_id": "unknown"}), load_registry())
    assert error.value.status_code == 404
    cfg = load_registry().model_copy(
        update={
            "sources": tuple(
                s.model_copy(
                    update={
                        "network_permission": "permitted",
                        "availability": "ready",
                        "acquisition_scope": "operator_smoke",
                        "acquisition_approved_until": datetime.now(UTC) + timedelta(hours=1),
                    }
                )
                if s.id == "osm"
                else s
                for s in load_registry().sources
            )
        }
    )
    assert validate(request(), cfg) == "Москва"
    for category in ("geo.vehicle_network", "geo.pedestrian_network", "economy.rent"):
        with pytest.raises(AcquisitionError, match="category_unsupported"):
            validate(request().model_copy(update={"category": category}), cfg)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "::ffff:8.8.8.8",
        "2002:0808:0808::1",
    ],
)
def test_nonpublic_addresses(ip: str) -> None:
    assert not network.public_address(ip)


def test_mixed_dns_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("8.8.8.8", 443)), (0, 0, 0, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(AcquisitionError, match="address_forbidden"):
        network.addresses()


@dataclass
class Response:
    status: int = 200
    content: bytes = b'{"test":true}'
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        self.reader = io.BytesIO(self.content)

    def getheader(self, name: str, default: Any = None) -> Any:
        return ({"Content-Type": "application/json"} | (self.headers or {})).get(name, default)

    def read1(self, count: int) -> bytes:
        return self.reader.read(count)


def install_response(monkeypatch: pytest.MonkeyPatch, response: Response) -> list[object]:
    calls: list[object] = []

    class Socket:
        def settimeout(self, seconds: int) -> None:
            pass

    class Connection:
        sock = Socket()

        def __init__(self, ip: str) -> None:
            assert ip == "8.8.8.8"

        def connect(self) -> None:
            pass

        def request(self, *args: object) -> None:
            calls.append(args)

        def getresponse(self) -> Response:
            return response

        def close(self) -> None:
            pass

    monkeypatch.setattr(network, "addresses", lambda: ("8.8.8.8",))
    monkeypatch.setattr(network, "PinnedHTTPS", Connection)
    return calls


@pytest.mark.parametrize(
    "response,code",
    [
        (
            Response(status=302, headers={"Location": "http://127.0.0.1/secret"}),
            "redirect_forbidden",
        ),
        (Response(headers={"Content-Encoding": "gzip"}), "encoding_forbidden"),
        (Response(headers={"Content-Type": "text/html"}), "format_invalid"),
        (Response(headers={"Content-Length": "1000"}), "size_exceeded"),
        (Response(content=b"x" * 21), "size_exceeded"),
        (Response(headers={"Content-Length": "15"}), "download_truncated"),
        (Response(status=429, headers={"Retry-After": "300"}), "source_http_error"),
    ],
)
def test_response_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, response: Response, code: str
) -> None:
    calls = install_response(monkeypatch, response)
    with pytest.raises(AcquisitionError, match=code) as error:
        network.fetch("fixture query", tmp_path / "data", 20, lambda: None)
    assert len(calls) == 1
    assert "127.0.0.1" not in str(error.value)
    if response.status == 429:
        assert error.value.retry_after == 300


def test_valid_download_and_no_url_argument(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_response(monkeypatch, Response())
    path = tmp_path / "ok"
    assert network.fetch("fixture query", path, 20, lambda: None) == 13
    assert path.read_bytes() == b'{"test":true}'
    with pytest.raises(AcquisitionError, match="endpoint_forbidden"):
        network.fetch("x", path, 20, lambda: None, endpoint="https://evil.example/")


def test_pinned_connect_preserves_sni_and_checks_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    class Raw:
        def settimeout(self, timeout: int) -> None:
            assert timeout == 5

        def connect(self, endpoint: object) -> None:
            assert endpoint == ("8.8.8.8", 443)

        def getpeername(self) -> tuple[str, int]:
            return ("8.8.8.8", 443)

        def close(self) -> None:
            pass

    class TLS:
        def wrap_socket(self, raw: Raw, *, server_hostname: str) -> Raw:
            assert server_hostname == "overpass-api.de"
            return raw

    monkeypatch.setattr(ssl, "create_default_context", lambda: TLS())
    monkeypatch.setattr(socket, "socket", lambda *a: Raw())
    conn = network.PinnedHTTPS("8.8.8.8")
    conn.connect()
    conn.close()
    monkeypatch.setattr(Raw, "getpeername", lambda self: ("127.0.0.1", 443))
    with pytest.raises(AcquisitionError, match="peer_mismatch"):
        network.PinnedHTTPS("8.8.8.8").connect()


def test_process_lock_proves_stopped_worker(tmp_path: Path) -> None:
    with ProcessLock(tmp_path) as first:
        identity = first.installation
        with pytest.raises(AcquisitionError, match="already_running"):
            with ProcessLock(tmp_path):
                pass
    with ProcessLock(tmp_path) as restarted:
        assert restarted.installation == identity


def test_operator_boundary_and_strict_input(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as client:
        monkeypatch.delenv("BA_ACQUISITION_ENABLED", raising=False)
        assert (
            client.get("/api/v2/acquisitions/00000000-0000-0000-0000-000000000001").status_code
            == 503
        )
        monkeypatch.setenv("BA_ACQUISITION_ENABLED", "1")
        token = secrets.token_urlsafe(32)
        monkeypatch.setenv("BA_ACQUISITION_OPERATOR_TOKEN", token)
        result = client.post("/api/v2/acquisitions", json=request().model_dump(mode="json"))
        assert result.status_code == 401 and result.headers["X-Request-ID"]
        for extra in ("url", "owner", "path", "sql"):
            result = client.post(
                "/api/v2/acquisitions",
                json=request().model_dump(mode="json") | {extra: "forbidden"},
                headers={"X-Acquisition-Token": token},
            )
            assert result.status_code == 422
    with pytest.raises(ValidationError):
        Resources(max_pending=3)


def test_expired_or_unknown_license_is_not_permission() -> None:
    cfg = load_registry()
    for update in (
        {"license_status": "review_required"},
        {"license_status": "forbidden"},
        {
            "network_permission": "permitted",
            "availability": "ready",
            "acquisition_scope": "operator_smoke",
            "acquisition_approved_until": datetime.now(UTC) - timedelta(seconds=1),
        },
    ):
        altered = cfg.model_copy(
            update={
                "sources": tuple(
                    s.model_copy(update=update) if s.id == "osm" else s for s in cfg.sources
                )
            }
        )
        with pytest.raises(AcquisitionError, match="source_not_permitted"):
            validate(request(), altered)


def test_network_timeout_and_cancel_are_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def timeout() -> tuple[str, ...]:
        raise TimeoutError("never disclose private diagnostics")

    monkeypatch.setattr(network, "addresses", timeout)
    with pytest.raises(AcquisitionError, match="network_timeout") as error:
        network.fetch("q", tmp_path / "timeout", 20, lambda: None)
    assert "private" not in str(error.value)

    def cancelled() -> None:
        raise AcquisitionError("acquisition_cancelled")

    with pytest.raises(AcquisitionError, match="acquisition_cancelled"):
        network.fetch("q", tmp_path / "cancelled", 20, cancelled)

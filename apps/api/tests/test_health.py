import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_session
from app.main import app


def test_health_reports_postgis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.main.check_postgis", lambda: "3.5 test")
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "postgis_version": "3.5 test",
    }


def test_health_returns_503_without_database_and_hides_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> None:
        raise psycopg.OperationalError("password=secret host=private-db")

    monkeypatch.setattr("app.main.check_postgis", fail)
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}


def test_business_api_database_failure_is_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    def unavailable() -> None:
        raise OperationalError(
            "INSERT private_statement", {"token": "private-secret"}, Exception("db")
        )

    app.dependency_overrides[get_session] = unavailable
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/api/v1/conversations")
        assert response.status_code == 503
        assert response.json() == {"detail": {"code": "database_unavailable"}}
        for secret in ("private_statement", "private-secret"):
            assert secret not in response.text
            assert secret not in caplog.text
    finally:
        app.dependency_overrides.pop(get_session)

import psycopg
from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_postgis(monkeypatch):
    monkeypatch.setattr("app.main.check_postgis", lambda: "3.5 test")
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "postgis_version": "3.5 test",
    }


def test_health_returns_503_without_database_and_hides_details(monkeypatch):
    def fail():
        raise psycopg.OperationalError("password=secret host=private-db")

    monkeypatch.setattr("app.main.check_postgis", fail)
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}

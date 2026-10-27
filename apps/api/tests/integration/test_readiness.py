"""H-05 actual PostGIS/schema probe, only disposable databases."""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app

from .support import isolated_database, migrate

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostgreSQL")


def test_actual_schema_mismatch_extension_missing_and_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with isolated_database() as database:
        monkeypatch.setenv("PGDATABASE", database)
        with TestClient(app) as client:
            response = client.get("/readyz")
            assert response.status_code == 503
            assert response.json()["postgis"] == "missing"
            assert response.json()["schema_status"] == "incompatible"
            migrate(database, "upgrade", "0007_data_providers")
            assert client.get("/readyz").json()["schema_status"] == "incompatible"
            migrate(database, "upgrade", "head")
            assert client.get("/readyz").status_code == 200
            # Schema remains unchanged by repeated probes, and no transaction survives.
            for _ in range(3):
                assert client.get("/readyz").status_code == 200
            with psycopg.connect(dbname="postgres", autocommit=True) as admin:
                assert admin.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname=%s AND state='idle in transaction'",
                    (database,),
                ).fetchone() == (0,)


def test_actual_unreachable_database_is_bounded_and_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "1")
    with TestClient(app) as client:
        assert client.get("/livez").status_code == 200
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
    assert "127.0.0.1" not in response.text

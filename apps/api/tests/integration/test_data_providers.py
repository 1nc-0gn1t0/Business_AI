import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.data.importer import import_dataset
from app.data.schemas import SyntheticDataset
from app.db.models import ProviderDatasetRecord
from app.db.session import get_session
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot
from app.main import app

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostGIS")
BASE = "/api/v1/data-providers"


def seed(slug: str = "demo-test", revision: str = "v1", days: int = 0) -> SyntheticDataset:
    generated = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=days)
    return SyntheticDataset.model_validate(
        {
            "slug": slug,
            "revision": revision,
            "source_name": "Test authored scenario",
            "generated_at": generated,
            "bbox": {"west": 49.11, "south": 55.78, "east": 49.12, "north": 55.79},
            "attribution": "Sab0tage — synthetic demonstration",
            "generation_method": "fixed-authored-scenario-v1",
            "limitations": ["Test synthetic only"],
            "measurements": [
                {
                    "metric": "rent_monthly_rub",
                    "value": 90000.0,
                    "unit": "RUB_per_month",
                    "origin": "synthetic",
                    "source_name": "Test authored scenario",
                    "observed_at": None,
                    "generated_at": generated,
                    "data_version": revision,
                    "confidence": "not_applicable",
                    "limitations": ["Test synthetic only"],
                }
            ],
        }
    )


@pytest.fixture(scope="module")
def imported(migrated_database: tuple[Engine, UUID]) -> Engine:
    engine, _ = migrated_database
    with Session(engine) as session, session.begin():
        manifest, document = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
        import_snapshot(session, manifest, document)
        import_dataset(session, seed())
    return engine


@pytest.fixture
def client(imported: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATA_DEMO_ENABLED", "true")

    def session() -> Iterator[Session]:
        with Session(imported) as db, db.begin():
            yield db

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session)


def test_shared_contract_real_counts_and_no_hidden_synthetic(
    client: TestClient, imported: Engine
) -> None:
    metadata = client.get(BASE + "/osm/datasets").json()[0]
    body = {
        "provider": "osm",
        "dataset": metadata["slug"],
        "data_version": metadata["data_version"],
        "metrics": ["mapped_poi_count", "mapped_cafe_count", "rent_monthly_rub"],
    }
    response = client.post(BASE + "/indicators", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    with imported.connect() as db:
        count = db.scalar(sa.text("SELECT count(*) FROM geo_pois"))
    assert result["indicators"][0]["measurement"]["value"] == count
    assert result["indicators"][0]["measurement"]["origin"] == "open_data"
    assert result["indicators"][2]["measurement"] is None
    assert result["indicators"][2]["status"] == "missing"
    assert (
        client.post(BASE + "/indicators", json=body).json()["request_fingerprint"]
        == result["request_fingerprint"]
    )
    body["bbox"] = {"west": 0, "south": 0, "east": 0.01, "north": 0.01}
    outside = client.post(BASE + "/indicators", json=body).json()
    assert all(
        i["status"] == "outside_coverage" and i["measurement"] is None
        for i in outside["indicators"]
    )
    body["data_version"] = "0" * 64
    assert client.post(BASE + "/indicators", json=body).status_code == 409


def test_demo_is_explicit_disabled_and_stale_remains_labelled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = client.get(BASE + "/synthetic/datasets").json()[0]
    body = {
        "provider": "synthetic",
        "dataset": metadata["slug"],
        "data_version": metadata["data_version"],
        "metrics": ["rent_monthly_rub", "mapped_poi_count"],
    }
    assert client.post(BASE + "/indicators", json=body).status_code == 403
    body["mode"] = "demo"
    result = client.post(BASE + "/indicators", json=body).json()
    metric = result["indicators"][0]
    assert metric["measurement"]["origin"] == "synthetic"
    assert metric["measurement"]["observed_at"] is None
    assert metric["measurement"]["data_version"] == metadata["data_version"]
    assert metric["status"] == "stale"
    assert result["indicators"][1]["measurement"] is None
    body["bbox"] = {"west": 49.11, "south": 55.78, "east": 49.115, "north": 55.785}
    assert (
        client.post(BASE + "/indicators", json=body).json()["indicators"][0]["status"]
        == "outside_coverage"
    )
    monkeypatch.setenv("DATA_DEMO_ENABLED", "false")
    assert client.post(BASE + "/indicators", json=body).status_code == 403
    assert client.post(BASE + "/selection", json={"mode": "demo"}).status_code == 403
    assert client.get(BASE + "/synthetic/datasets").json() == []
    assert client.post(BASE + "/selection", json={"mode": "real"}).status_code == 200


def test_future_providers_are_unavailable_not_fabricated(client: TestClient) -> None:
    sources = {s["id"]: s for s in client.get(BASE + "/sources").json()}
    for provider in ("ghsl", "licensed"):
        assert sources[provider]["status"] == "not_integrated"
        assert client.get(f"{BASE}/{provider}/datasets").json() == []
        response = client.post(
            BASE + "/indicators",
            json={
                "provider": provider,
                "dataset": "missing",
                "data_version": "0" * 64,
                "metrics": ["mapped_poi_count"],
            },
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "provider_not_integrated"


def test_replay_conflict_history_and_tamper_fail_closed(
    imported: Engine, client: TestClient
) -> None:
    original = seed("version-test")
    with Session(imported) as db, db.begin():
        first = import_dataset(db, original)
        assert import_dataset(db, original) == first
    changed = original.model_dump()
    changed["measurements"][0]["value"] = 95000.0
    with Session(imported) as db, db.begin(), pytest.raises(ValueError, match="different content"):
        import_dataset(db, SyntheticDataset.model_validate(changed))
    with Session(imported) as db, db.begin():
        second = import_dataset(db, seed("version-test", "v2", 1))
        assert import_dataset(db, original) == first  # Historical replay does not roll back active.
        assert db.get(ProviderDatasetRecord, ("synthetic", "version-test", first)).active is False  # type: ignore[union-attr]
        assert db.get(ProviderDatasetRecord, ("synthetic", "version-test", second)).active is True  # type: ignore[union-attr]
    for version in (first, second):
        response = client.post(
            BASE + "/indicators",
            json={
                "provider": "synthetic",
                "mode": "demo",
                "dataset": "version-test",
                "data_version": version,
                "metrics": ["rent_monthly_rub"],
            },
        )
        assert response.status_code == 200
        assert response.json()["dataset"]["data_version"] == version
    with Session(imported) as db, db.begin():
        row = db.get(ProviderDatasetRecord, ("synthetic", "version-test", second))
        assert row is not None
        row.document = dict(row.document) | {"source_name": "tampered"}
    response = client.post(
        BASE + "/indicators",
        json={
            "provider": "synthetic",
            "mode": "demo",
            "dataset": "version-test",
            "data_version": second,
            "metrics": ["rent_monthly_rub"],
        },
    )
    assert response.status_code == 503


def test_demo_selection_does_not_change_existing_geo_algorithms(client: TestClient) -> None:
    body = {
        "candidates": {
            "profile": {
                "conversation_id": "00000000-0000-0000-0000-000000000008",
                "city": "Казань",
                "category": "кофейня",
                "budget": "2000000",
                "confirmation_state": "confirmed",
            },
            "cell_size_m": 250,
            "min_separation_m": 0,
            "limit": 3,
        },
        "scoring": {
            "radius_m": 50,
            "competitor_mode": "cluster",
            "weights": {"transit": 0, "infrastructure": 0, "complementary": 0, "competitors": 1},
        },
    }
    base = "/api/v1/geo/kazan-fixture"
    before = client.post(base + "/rankings", json=body).json()
    walk_before = client.post(base + "/walking-rankings", json={"ranking": body}).json()
    assert client.post(BASE + "/selection", json={"mode": "demo"}).status_code == 200
    after = client.post(base + "/rankings", json=body).json()
    walk_after = client.post(base + "/walking-rankings", json={"ranking": body}).json()
    assert before["request_fingerprint"] == after["request_fingerprint"]
    assert [
        (e["candidate_id"], e["score"], e["rank"], e["raw"]) for e in before["evaluations"]
    ] == [(e["candidate_id"], e["score"], e["rank"], e["raw"]) for e in after["evaluations"]]
    assert (
        walk_before["network"]["request_fingerprint"]
        == walk_after["network"]["request_fingerprint"]
    )
    assert [e["score"] for e in walk_before["network"]["evaluations"]] == [
        e["score"] for e in walk_after["network"]["evaluations"]
    ]

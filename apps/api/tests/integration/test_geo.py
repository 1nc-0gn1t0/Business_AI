import copy
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import GeoDatasetRecord
from app.db.session import get_session
from app.geo.ingest import import_snapshot
from app.geo.provider import GeoImportError, load_snapshot
from app.main import app

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostGIS")
FIXTURE = Path(__file__).parent / "fixtures/kazan.raw.json"
BOUNDARY = Path(__file__).parent / "fixtures/kazan-boundary.raw.json"


@pytest.fixture(scope="module")
def imported(migrated_database: tuple[Engine, UUID]) -> Engine:
    engine, _ = migrated_database
    with Session(engine) as session, session.begin():
        for path in (FIXTURE, BOUNDARY):
            manifest, document = load_snapshot(path)
            import_snapshot(session, manifest, document)
    return engine


@pytest.fixture
def client(imported: Engine) -> Iterator[TestClient]:
    def session() -> Iterator[Session]:
        with Session(imported) as db, db.begin():
            yield db

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session)


def test_real_osm_bbox_category_radius_and_provenance(client: TestClient) -> None:
    base = "/api/v1/geo/kazan-fixture"
    response = client.get(
        base + "/pois", params={"bbox": "49.115,55.785,49.12,55.79", "category": "amenity:cafe"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["features"]
    assert data["dataset"]["origin"] == "open_data"
    assert data["dataset"]["license"] == "ODbL-1.0"
    assert data["dataset"]["attribution"] == "© OpenStreetMap contributors"
    assert data["dataset"]["osm_base"]
    for feature in data["features"]:
        assert "amenity:cafe" in feature["properties"]["categories"]
        assert feature["properties"]["osm_version"] > 0
        assert feature["properties"]["observed_at"]
    first = data["features"][0]
    lon, lat = first["geometry"]["coordinates"]
    nearby = client.get(
        base + "/pois",
        params={
            "longitude": lon,
            "latitude": lat,
            "radius_m": 1,
        },
    ).json()["features"]
    assert first["id"] in {row["id"] for row in nearby}
    assert all(row["properties"]["distance_m"] <= 1 for row in nearby)
    empty = client.get(base + "/pois", params={"bbox": "49,55.6,49.01,55.61"}).json()
    assert empty["features"] == []
    assert empty["dataset"]["limitations"]
    assert "traffic" not in data and "demand" not in data


def test_pagination_version_pinning_and_missing_data(client: TestClient) -> None:
    path = "/api/v1/geo/kazan-fixture/pois"
    params: dict[str, str | int] = {"bbox": "49.115,55.785,49.12,55.79", "limit": 2}
    first = client.get(path, params=params).json()
    assert first["next_offset"] == 2
    assert client.get(path, params=params | {"offset": 2}).status_code == 422
    second = client.get(
        path,
        params=params
        | {
            "offset": 2,
            "data_version": first["dataset"]["data_version"],
        },
    ).json()
    assert {x["id"] for x in first["features"]}.isdisjoint(x["id"] for x in second["features"])
    assert client.get(path, params=params | {"data_version": "0" * 64}).status_code == 409
    assert client.get("/api/v1/geo/absent/pois", params=params).status_code == 404
    assert client.get(path, params={"district_id": 999999999}).status_code == 404
    assert client.get(path, params={"radius_m": 100}).status_code == 422
    assert client.get(path, params=params | {"category": "' OR true --"}).json()["features"] == []
    assert client.get("/api/v1/geo/kazan-fixture/categories").json()["categories"]


def test_real_boundaries_support_district_query(client: TestClient) -> None:
    base = "/api/v1/geo/kazan-boundary-fixture"
    districts = client.get(base + "/districts").json()
    assert districts["features"]
    for district in districts["features"]:
        assert district["geometry"]["type"] == "MultiPolygon"
        assert district["properties"]["admin_level"] in {8, 9, 10}
        response = client.get(
            base + "/pois",
            params={
                "district_id": district["properties"]["osm_id"],
            },
        )
        assert response.status_code == 200
        assert response.json()["dataset"]["data_version"] == districts["dataset"]["data_version"]


def test_import_replay_and_atomic_update(imported: Engine) -> None:
    manifest, document = load_snapshot(FIXTURE)
    with Session(imported) as session, session.begin():
        original = import_snapshot(session, manifest, document)
        original_id, original_count = original.id, original.poi_count
    with Session(imported) as session, session.begin():
        repeated = import_snapshot(session, manifest, document)
        assert repeated.id == original_id and repeated.poi_count == original_count
    fresh = manifest.model_copy(
        update={
            "sha256": "a" * 64,
            "osm_base": manifest.osm_base + timedelta(seconds=1),
            "fetched_at": manifest.fetched_at + timedelta(seconds=1),
        }
    )
    # Synthetic mutation only inside isolated test DB: test replacement/deletion semantics.
    updated = copy.deepcopy(document)
    updated["elements"] = [row for row in updated["elements"] if row.get("type") == "node"][:1]
    with Session(imported) as session:
        with pytest.raises(GeoImportError):
            with session.begin():
                import_snapshot(session, fresh, {"elements": []})
    with Session(imported) as session, session.begin():
        original_record = session.get(GeoDatasetRecord, original_id)
        assert original_record is not None and original_record.active
        new = import_snapshot(session, fresh, updated)
        assert new.poi_count == 1
        assert (
            session.scalar(
                sa.text("SELECT count(*) FROM geo_pois WHERE dataset_id=:id"), {"id": original_id}
            )
            == original_count
        )
    with Session(imported) as session:
        with pytest.raises(GeoImportError, match="Older"):
            with session.begin():
                import_snapshot(session, manifest, document)


def test_concurrent_replay_creates_one_snapshot(imported: Engine) -> None:
    manifest, document = load_snapshot(FIXTURE)
    manifest = manifest.model_copy(update={"slug": "concurrent-test"})

    def run() -> UUID:
        with Session(imported) as session, session.begin():
            return import_snapshot(session, manifest, document).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: run(), range(2)))
    assert ids[0] == ids[1]


def test_incomplete_geometry_is_reported_not_invented(imported: Engine) -> None:
    manifest, document = load_snapshot(BOUNDARY)
    changed = copy.deepcopy(document)
    for element in changed["elements"]:
        if element.get("tags", {}).get("boundary"):
            element["members"] = []
        elif element["type"] == "node":
            element.pop("lat", None)
    manifest = manifest.model_copy(update={"slug": "incomplete-test", "sha256": "b" * 64})
    with Session(imported) as session, session.begin():
        record = import_snapshot(session, manifest, changed, allow_empty=True)
        assert record.district_count == 0
        assert record.diagnostics["incomplete_boundary"] > 0
        assert record.diagnostics["missing_location"] > 0

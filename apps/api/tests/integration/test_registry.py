"""Small artificial OSM/topology fixtures; no real Moscow data or external fetch."""

import os
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.bank.matching import digest
from app.data.coverage import coverage, read_metadata, spatial_fits
from app.data.importer import import_dataset
from app.data.registry import load_registry
from app.data.registry_schemas import CoverageQuery
from app.db.session import get_session
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot
from app.geo.schemas import Bounds
from app.geo.walk_import import import_graph, query
from app.geo.walk_schemas import WalkManifest
from app.main import app

from .support import migrate
from .test_conversations import create
from .test_data_providers import seed
from .test_populated_upgrade import fingerprints
from .test_walking import topology

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostGIS")
BASE = "/api/v2/data-registry/coverage"


@pytest.fixture(scope="module")
def registry_database(migrated_database: tuple[Engine, UUID]) -> tuple[Engine, Bounds]:
    engine, _ = migrated_database
    with Session(engine) as db, db.begin():
        manifest, document = load_snapshot(Path(__file__).parent / "fixtures/kazan.raw.json")
        import_snapshot(db, manifest, document)
        graph_manifest, graph_document = topology(manifest.slug)
        old_box = graph_manifest.bbox
        for item in graph_document["elements"]:
            if item["type"] == "node":
                item["lon"] = manifest.bbox.west + (item["lon"] - old_box.west) / (
                    old_box.east - old_box.west
                ) * (manifest.bbox.east - manifest.bbox.west)
                item["lat"] = manifest.bbox.south + (item["lat"] - old_box.south) / (
                    old_box.north - old_box.south
                ) * (manifest.bbox.north - manifest.bbox.south)
        graph_manifest = WalkManifest.model_validate(
            graph_manifest.model_dump()
            | {
                "city": manifest.city,
                "bbox": manifest.bbox,
                "query": query(manifest.bbox),
                "sha256": digest(graph_document),
                "source_sha256": digest(graph_document),
            }
        )
        import_graph(db, graph_manifest, graph_document)
        import_dataset(db, seed("registry-scenario-fixture"))
    return engine, manifest.bbox


@pytest.fixture
def registry_client(
    registry_database: tuple[Engine, Bounds], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("DATA_DEMO_ENABLED", "true")
    engine, _ = registry_database

    def session() -> Iterator[Session]:
        with Session(engine) as db, db.begin():
            yield db

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session)


def test_postgis_coverage_uses_extent_not_city_and_no_objects_scan(
    registry_client: TestClient, registry_database: tuple[Engine, Bounds]
) -> None:
    engine, bbox = registry_database
    sql_calls: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        many: bool,
    ) -> None:
        sql_calls.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        response = registry_client.post(
            BASE, json={"aoi": bbox.model_dump(), "categories": ["geo.mapped_poi"]}
        )
        assert response.status_code == 200
        item = response.json()["assessments"][0]
        assert item["local_status"] == "available"
        assert item["completeness"] == "full_for_requested_scope"
        assert item["object_quality"] == "unknown"
        assert item["datasets"][0]["observed_at"] is None
        assert item["datasets"][0]["source_timestamp"]
        # A false city label cannot move a real AOI to another place or claim Moscow ready.
        same = registry_client.post(
            BASE,
            json={
                "territory": "ru-moscow",
                "aoi": bbox.model_dump(),
                "categories": ["geo.mapped_poi"],
            },
        )
        assert same.json()["assessments"][0]["local_status"] == "unknown"
        assert (
            same.json()["assessments"][0]["datasets"][0]["spatial_fit"]
            == "full_for_requested_scope"
        )
        assert not same.json()["assessments"][0]["datasets"][0]["usable"]
        assert any("ST_Covers" in statement for statement in sql_calls)
        assert not any(
            "geo_pois" in statement or "walk_edges" in statement for statement in sql_calls
        )
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)


def test_kazan_identity_is_partial_and_moscow_no_import_missing(
    registry_client: TestClient,
) -> None:
    for territory, expected in (("ru-kazan", "partial"), ("ru-moscow", "missing")):
        result = registry_client.post(
            BASE,
            json={"territory": territory, "categories": ["geo.mapped_poi", "geo.vehicle_network"]},
        )
        assert result.status_code == 200
        mapped, vehicle = result.json()["assessments"]
        assert mapped["local_status"] == expected
        assert vehicle["local_status"] == "missing"
        if territory == "ru-moscow":
            assert not mapped["datasets"]
            assert mapped["acquisition"][0]["potentially_available"]


def test_partial_outside_and_exact_boundary(
    registry_client: TestClient, registry_database: tuple[Engine, Bounds]
) -> None:
    _, box = registry_database
    partial = box.model_dump() | {"west": box.west - 0.001}
    outside = {"west": 37.60, "east": 37.61, "south": 55.75, "north": 55.76}
    for aoi, expected in ((partial, "partial"), (outside, "missing")):
        result = registry_client.post(BASE, json={"aoi": aoi, "categories": ["geo.mapped_poi"]})
        assert result.json()["assessments"][0]["local_status"] == expected


def test_pedestrian_graph_is_not_vehicle_coverage(registry_client: TestClient) -> None:
    result = registry_client.post(
        BASE,
        json={
            "aoi": {"west": 49.115, "east": 49.12, "south": 55.78, "north": 55.79},
            "categories": ["geo.pedestrian_network", "geo.vehicle_network"],
        },
    )
    pedestrian, vehicle = result.json()["assessments"]
    assert pedestrian["datasets"] and pedestrian["freshness"] == "unknown"
    assert not vehicle["datasets"] and vehicle["local_status"] == "missing"


def test_synthetic_opt_in_never_becomes_observation(registry_client: TestClient) -> None:
    query: dict[str, object] = {"categories": ["scenario.finance"]}
    assert not registry_client.post(BASE, json=query).json()["assessments"][0]["datasets"]
    query["mode"] = "demo"
    response = registry_client.post(BASE, json=query)
    evidence = response.json()["assessments"][0]["datasets"][0]
    assert evidence["metadata"]["origin"] == "synthetic"
    assert evidence["observed_at"] is None and evidence["source_timestamp"] is None


def test_private_inputs_and_other_owner_ids_are_not_exposed(registry_client: TestClient) -> None:
    first, headers, _ = create(registry_client)
    second, other, _ = create(registry_client)
    assert first["id"] != second["id"]
    query = {"categories": ["user.budget", "user.costs"]}
    for token in (headers, other, {}):
        response = registry_client.post(BASE, json=query, headers=token)
        assert response.status_code == 200
        assert all(
            a["local_status"] == "unknown" and not a["datasets"]
            for a in response.json()["assessments"]
        )
        assert first["id"] not in response.text and second["access_token"] not in response.text
    rejected = registry_client.post(
        BASE, json=query | {"conversation_id": second["id"]}, headers=headers
    )
    assert rejected.status_code == 422
    assert second["id"] not in rejected.text


def test_no_fetch_or_llm_and_invalid_category_has_no_sql(
    registry_client: TestClient,
    registry_database: tuple[Engine, Bounds],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.adapters import llm
    from app.geo.provider import OverpassProvider
    from app.services import dialogue

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Coverage must not invoke model/network")

    monkeypatch.setattr(llm, "get_llm", forbidden)
    monkeypatch.setattr(dialogue, "get_llm", forbidden)
    monkeypatch.setattr(OverpassProvider, "fetch", forbidden)
    engine, box = registry_database
    assert (
        registry_client.post(
            BASE, json={"aoi": box.model_dump(), "categories": ["geo.mapped_poi"]}
        ).status_code
        == 200
    )
    statements: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        many: bool,
    ) -> None:
        statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        response = registry_client.post(BASE, json={"categories": ["unknown-category"]})
        assert response.status_code == 422 and not statements
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)


def test_reads_and_repeated_upgrade_preserve_all_table_fingerprints(
    registry_client: TestClient, registry_database: tuple[Engine, Bounds]
) -> None:
    engine, box = registry_database
    with engine.connect() as connection:
        name = connection.scalar(sa.text("SELECT current_database()"))
    assert isinstance(name, str) and name.startswith("business_ai_test_")
    before = fingerprints(name)
    legacy = registry_client.get("/api/v1/geo/datasets").json()
    assert (
        registry_client.post(
            BASE, json={"aoi": box.model_dump(), "categories": ["geo.mapped_poi"]}
        ).status_code
        == 200
    )
    assert registry_client.get("/api/v1/geo/datasets").json() == legacy
    migrate(name, "upgrade", "head")
    migrate(name, "check")
    assert fingerprints(name) == before


def test_metadata_cap_is_unknown_not_false_missing(
    registry_database: tuple[Engine, Bounds],
) -> None:
    engine, box = registry_database
    cfg = load_registry().model_copy(update={"max_datasets": 1})
    with Session(engine) as db:
        records, complete = read_metadata(db, 1, True)
        assert len(records) == 1 and not complete
        result = coverage(
            db, CoverageQuery(territory="ru-moscow", categories=("geo.mapped_poi",)), cfg
        )
        assert result.assessments[0].local_status == "unknown"
        assert (
            spatial_fits(db, CoverageQuery(aoi=box, categories=("geo.mapped_poi",)), records)[0]
            == "full_for_requested_scope"
        )


def test_small_fixture_latency(registry_database: tuple[Engine, Bounds]) -> None:
    engine, box = registry_database
    times = []
    with Session(engine) as db:
        for _ in range(20):
            start = time.perf_counter()
            result = coverage(
                db, CoverageQuery(aoi=box, categories=("geo.mapped_poi",)), load_registry()
            )
            assert result.assessments[0].local_status == "available"
            times.append((time.perf_counter() - start) * 1000)
    # Evidence, not a hardware-independent production SLA.
    print(
        f"U01 small artificial fixture n=20 median_ms={sorted(times)[10]:.3f} "
        f"max_ms={max(times):.3f}"
    )

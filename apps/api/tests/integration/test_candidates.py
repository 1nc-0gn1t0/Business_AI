import json
import math
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import GeoDatasetRecord, GeoPOIRecord
from app.db.session import get_session
from app.geo.candidate_schemas import CandidateRequest
from app.geo.candidates import generate
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot
from app.main import app

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostGIS")
FIXTURES = Path(__file__).parent / "fixtures"
PATH = "/api/v1/geo/kazan-fixture/candidates"


@pytest.fixture(scope="module")
def imported(migrated_database: tuple[Engine, UUID]) -> Engine:
    engine, _ = migrated_database
    with Session(engine) as session, session.begin():
        for name in ("kazan.raw.json", "kazan-boundary.raw.json"):
            manifest, document = load_snapshot(FIXTURES / name)
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


def body() -> dict[str, object]:
    return {
        "profile": {
            "conversation_id": str(uuid4()),
            "city": "Казань",
            "category": "кофейня",
            "budget": "2000000",
        },
        "cell_size_m": 250,
        "min_separation_m": 0,
        "limit": 3,
    }


def test_multiple_valid_covered_unique_reproducible_zones(
    client: TestClient, imported: Engine
) -> None:
    request = body()
    response = client.post(PATH, json=request)
    assert response.status_code == 200, response.text
    data = response.json()
    features = data["features"]
    assert len(features) == 3, data
    assert data["status"] == "ok"
    assert data["metric_srid"] == 32639
    assert data["dataset"]["origin"] == "open_data"
    assert data["algorithm_version"] == "utm-grid-dispersion-v1"
    assert len({f["id"] for f in features}) == 3
    assert len({json.dumps(f["geometry"], sort_keys=True) for f in features}) == 3
    assert client.post(PATH, json=body()).json()["features"] == features
    assert data["not_evaluated"]
    with imported.connect() as connection:
        for feature in features:
            row = connection.execute(
                sa.text("""
                WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:g),4326) geom),
                d AS (SELECT ST_MakeEnvelope(49.115,55.785,49.12,55.79,4326) geom)
                SELECT ST_IsValid(g.geom),ST_Covers(d.geom,g.geom),
                 ST_Covers(g.geom,ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)),
                 ST_Area(ST_Transform(g.geom,32639)) FROM g,d
            """),
                {
                    "g": json.dumps(feature["geometry"]),
                    "point": json.dumps(feature["properties"]["representative_point"]),
                },
            ).one()
            assert row[0] and row[1] and row[2]
            assert row[3] == pytest.approx(feature["properties"]["area_m2"], abs=0.01)
            assert feature["properties"]["anchor"]["properties"]["osm_version"] > 0
            assert feature["properties"]["kind"] == "geographic_zone_not_premises"


def test_separation_and_positive_proximity(client: TestClient, imported: Engine) -> None:
    data = client.post(
        PATH,
        json=body()
        | {
            "min_separation_m": 200,
            "requirements": [{"category": "amenity:cafe", "max_distance_m": 300, "min_count": 1}],
        },
    ).json()
    assert len(data["features"]) >= 2, data
    points = [f["properties"]["representative_point"]["coordinates"] for f in data["features"]]
    for a in points:
        for b in points:
            if a != b:
                # Independent approximate great-circle distance on this small fixture.
                distance = 6371000 * math.hypot(
                    math.radians(a[0] - b[0]) * math.cos(math.radians(a[1])),
                    math.radians(a[1] - b[1]),
                )
                assert distance > 199
    assert all(f["properties"]["requirements"][0]["mapped_count"] >= 1 for f in data["features"])
    with imported.connect() as connection:
        for f in data["features"]:
            count = connection.scalar(
                sa.text("""SELECT count(*) FROM geo_pois p
                JOIN geo_datasets d ON d.id=p.dataset_id WHERE d.slug='kazan-fixture'
                AND d.active AND p.categories @> ARRAY['amenity:cafe']
                AND ST_DWithin(p.geom::geography,
                 ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)::geography,300)"""),
                {"point": json.dumps(f["properties"]["representative_point"])},
            )
            assert count == f["properties"]["requirements"][0]["mapped_count"]
    none = client.post(
        PATH,
        json=body() | {"requirements": [{"category": "amenity:nonexistent", "max_distance_m": 1}]},
    ).json()
    assert none["status"] == "no_candidates" and none["features"] == []


def test_coverage_empty_and_partial(client: TestClient) -> None:
    outside = {"west": 49, "south": 55.6, "east": 49.01, "north": 55.61}
    data = client.post(PATH, json=body() | {"search_bbox": outside}).json()
    assert data["status"] == "no_candidates", data
    wider = {"west": 49.114, "south": 55.784, "east": 49.121, "north": 55.791}
    data = client.post(PATH, json=body() | {"search_bbox": wider}).json()
    assert data["features"] and data["status"] == "partial"
    assert "requested_region_clipped_to_coverage" in data["reasons"]


def test_missing_profile_districts_constraints_versions(client: TestClient) -> None:
    for profile, reason in [
        ({"city": None}, "profile_city_and_category_required"),
        ({"city": "Москва"}, "profile_city_differs_from_dataset"),
        ({"category": "неизвестно"}, "unsupported_business_category"),
        (
            {"preferences": {"preferred_districts": ["неизвестный"]}},
            "preferred_district_missing_or_ambiguous",
        ),
        ({"preferences": {"constraints": ["аренда до 50000"]}}, "unmapped_profile_constraints"),
    ]:
        request = body()
        original = request["profile"]
        assert isinstance(original, dict)
        assert isinstance(profile, dict)
        request["profile"] = original | profile
        data = client.post(PATH, json=request).json()
        assert data["features"] == [] and reason in data["reasons"], data
    data = client.post(PATH, json=body() | {"district_ids": [9999999]}).json()
    assert data["status"] == "insufficient_data"
    assert client.post(PATH, json=body() | {"data_version": "0" * 64}).status_code == 409
    assert client.post("/api/v1/geo/missing/candidates", json=body()).status_code == 404
    assert client.post(PATH, json=body() | {"cell_size_m": -1}).status_code == 422


def test_district_intersection_and_exclusion(client: TestClient, imported: Engine) -> None:
    path = "/api/v1/geo/kazan-boundary-fixture/candidates"
    districts = client.get("/api/v1/geo/kazan-boundary-fixture/districts").json()["features"]
    district = next(d for d in districts if d["properties"]["osm_id"] == 2133462)
    data = client.post(path, json=body() | {"district_ids": [2133462]}).json()
    assert data["features"], data
    with imported.connect() as connection:
        for f in data["features"]:
            assert connection.scalar(
                sa.text("""SELECT ST_Covers(
                ST_SetSRID(ST_GeomFromGeoJSON(:d),4326),
                ST_SetSRID(ST_GeomFromGeoJSON(:g),4326))"""),
                {"d": json.dumps(district["geometry"]), "g": json.dumps(f["geometry"])},
            )
    empty = client.post(
        path, json=body() | {"district_ids": [2133462], "excluded_district_ids": [2133462]}
    ).json()
    assert empty["features"] == [] and empty["status"] == "no_candidates"
    assert data["status"] == "partial"
    assert "requested_region_clipped_to_coverage" in data["reasons"]
    outside = client.post(path, json=body() | {"excluded_district_ids": [2133462]}).json()
    assert outside["status"] in ("ok", "partial", "no_candidates"), outside
    with imported.connect() as connection:
        for f in outside["features"]:
            assert connection.scalar(
                sa.text("""SELECT ST_Disjoint(
                ST_SetSRID(ST_GeomFromGeoJSON(:d),4326),
                ST_SetSRID(ST_GeomFromGeoJSON(:g),4326))"""),
                {"d": json.dumps(district["geometry"]), "g": json.dumps(f["geometry"])},
            )
    preferred = body()
    profile = preferred["profile"]
    assert isinstance(profile, dict)
    profile["preferences"] = {"preferred_districts": [district["properties"]["name"]]}
    by_name = client.post(path, json=preferred).json()
    assert [f["geometry"] for f in by_name["features"]] == [f["geometry"] for f in data["features"]]


def test_bound_constraint_and_empty_observations(client: TestClient, imported: Engine) -> None:
    request = body()
    profile = request["profile"]
    assert isinstance(profile, dict)
    profile["preferences"] = {"constraints": ["рядом с кафе"]}
    request["requirements"] = [
        {"category": "amenity:cafe", "max_distance_m": 500, "profile_constraint": "рядом с кафе"}
    ]
    assert client.post(PATH, json=request).json()["features"]
    with Session(imported) as session:
        record = session.scalar(
            sa.select(GeoDatasetRecord).where(
                GeoDatasetRecord.slug == "kazan-fixture", GeoDatasetRecord.active
            )
        )
        assert record is not None
        session.execute(sa.delete(GeoPOIRecord).where(GeoPOIRecord.dataset_id == record.id))
        result = generate(session, "kazan-fixture", CandidateRequest.model_validate(body()))
        assert result.status == "no_candidates" and not result.features
        session.rollback()


def test_grid_resource_limit(imported: Engine) -> None:
    with Session(imported) as session:
        record = session.scalar(
            sa.select(GeoDatasetRecord).where(
                GeoDatasetRecord.slug == "kazan-fixture", GeoDatasetRecord.active
            )
        )
        assert record is not None
        record.bbox = {"west": 0, "south": 0, "east": 2.8, "north": 0.035}
        session.flush()
        with pytest.raises(HTTPException) as error:
            generate(session, "kazan-fixture", CandidateRequest.model_validate(body()))
        assert error.value.status_code == 422
        assert isinstance(error.value.detail, dict)
        assert error.value.detail["code"] == "candidate_grid_too_large"
        session.rollback()

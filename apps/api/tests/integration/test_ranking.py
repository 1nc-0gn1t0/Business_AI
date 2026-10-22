import copy
import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import GeoPOIRecord
from app.db.session import get_session
from app.geo.ingest import import_snapshot
from app.geo.provider import load_snapshot
from app.main import app

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostGIS")
FIXTURE = Path(__file__).parent / "fixtures/kazan.raw.json"
PATH = "/api/v1/geo/kazan-fixture/rankings"


@pytest.fixture(scope="module")
def imported(migrated_database: tuple[Engine, UUID]) -> Engine:
    engine, _ = migrated_database
    with Session(engine) as session, session.begin():
        manifest, document = load_snapshot(FIXTURE)
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
        # Tiny real fixture: radius 50 m, coffee count only, explicit cluster hypothesis.
        "scoring": {
            "radius_m": 50,
            "competitor_mode": "cluster",
            "weights": {"transit": 0, "infrastructure": 0, "complementary": 0, "competitors": 1},
        },
    }


def test_real_metrics_independent_sql_and_provenance(client: TestClient, imported: Engine) -> None:
    response = client.post(PATH, json=body())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] in ("ok", "partial"), data
    assert len(data["comparison_ids"]) >= 2
    assert data["policy"]["competitors"] == ["amenity:cafe"]
    features = {f["id"]: f for f in data["candidates"]["features"]}
    with imported.connect() as connection:
        for result in data["evaluations"]:
            point = features[result["candidate_id"]]["properties"]["representative_point"]
            row = connection.execute(
                sa.text("""SELECT count(*),min(ST_Distance(
                p.geom::geography,ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)::geography))
                FROM geo_pois p JOIN geo_datasets d ON d.id=p.dataset_id
                WHERE d.slug='kazan-fixture' AND d.active
                AND p.categories @> ARRAY['amenity:cafe'] AND ST_DWithin(p.geom::geography,
                  ST_SetSRID(ST_GeomFromGeoJSON(:point),4326)::geography,50)"""),
                {"point": json.dumps(point)},
            ).one()
            assert result["raw"]["competitor_count"] == row[0]
            if row[1] is None:
                assert result["raw"]["nearest_competitor_m"] is None
            else:
                assert result["raw"]["nearest_competitor_m"] == pytest.approx(row[1])
            assert result["provenance"]["origin"] == "open_data"
            assert (
                result["provenance"]["data_version"]
                == data["candidates"]["dataset"]["data_version"]
            )
            assert result["origin"] == "modelled"
            assert "rent_and_budget_feasibility" in result["missing_data"]
            assert len(result["explanations"]) == 4
            counts = result["raw"]["category_counts"]
            assert counts.get("amenity:cafe", 0) == result["raw"]["competitor_count"]
            assert counts.get("highway:bus_stop", 0) == result["raw"]["transit_count"]
            assert result["algorithm_version"] == data["algorithm_version"]
            assert result["policy_fingerprint"] == data["policy"]["fingerprint"]
            if result["score"] is not None:
                assert result["raw"]["coverage_margin_m"] >= 51
                assert result["score"] == pytest.approx(
                    sum(c["contribution"] or 0 for c in result["components"]), abs=0.000001
                )


def test_determinism_pinning_budget_and_equal_score_order(client: TestClient) -> None:
    request = body()
    first = client.post(PATH, json=request).json()
    second = client.post(PATH, json=request).json()
    assert first["request_fingerprint"] == second["request_fingerprint"]
    for a, b in zip(first["evaluations"], second["evaluations"], strict=True):
        for key in ("candidate_id", "rank", "score", "components", "raw", "explanations"):
            assert a[key] == b[key]
    ordered = [
        (r["score"] is None, -(r["score"] or 0), r["candidate_id"]) for r in first["evaluations"]
    ]
    assert ordered == sorted(ordered)
    changed = copy.deepcopy(request)
    candidates = changed["candidates"]
    assert isinstance(candidates, dict)
    candidates["profile"]["budget"] = "3000000"
    third = client.post(PATH, json=changed).json()

    # IDs include budget; compare by geometric grid indices.
    def scores(data: dict[str, object]) -> list[float | None]:
        evaluations = data["evaluations"]
        assert isinstance(evaluations, list)
        return sorted([r["score"] for r in evaluations if r["score"] is not None])

    assert scores(first) == scores(third)
    candidates["data_version"] = "0" * 64
    assert client.post(PATH, json=changed).status_code == 409


def test_profile_confirmation_category_and_bad_requests(client: TestClient) -> None:
    request = body()
    candidates = request["candidates"]
    assert isinstance(candidates, dict)
    candidates["profile"]["confirmation_state"] = "draft"
    data = client.post(PATH, json=request).json()
    assert data["status"] == "needs_confirmation" and data["evaluations"] == []
    candidates["profile"]["confirmation_state"] = "confirmed"
    candidates["profile"]["category"] = "пекарня"
    data = client.post(PATH, json=request).json()
    assert data["policy"]["competitors"] == ["shop:bakery"]
    assert all(
        e["raw"]["competitor_count"] == e["raw"]["category_counts"].get("shop:bakery", 0)
        for e in data["evaluations"]
    )
    assert (
        client.post(PATH, json=body() | {"scoring": {"weights": {"competitors": 1}}}).status_code
        == 422
    )
    assert client.post("/api/v1/geo/missing/rankings", json=body()).status_code == 404


def test_coverage_incomparability_missing_signal_and_empty(client: TestClient) -> None:
    # The fixture is much smaller than a 500 m circle, so no scores are allowed.
    request = body()
    request["scoring"] = {"radius_m": 500}
    data = client.post(PATH, json=request).json()
    assert data["status"] == "insufficient_data"
    assert all(r["score"] is None and r["rank"] is None for r in data["evaluations"])
    assert all(r["status"] == "outside_coverage" for r in data["evaluations"])
    request["scoring"] = {
        "radius_m": 50,
        "weights": {"transit": 1, "infrastructure": 0, "complementary": 0},
    }
    data = client.post(PATH, json=request).json()
    assert data["status"] == "insufficient_data"  # fixture has no bus stops
    assert not data["comparison_ids"]
    candidates = request["candidates"]
    assert isinstance(candidates, dict)
    candidates["search_bbox"] = {"west": 49, "east": 49.01, "south": 55, "north": 55.01}
    data = client.post(PATH, json=request).json()
    assert data["status"] == "no_candidates" and data["evaluations"] == []


def test_synthetic_controlled_counts_weights_and_ties(
    client: TestClient,
    imported: Engine,
) -> None:
    # Deliberately synthetic test-only tags on existing test geometry, rolled back afterwards.
    # This fixture is not exported or used for the real Kazan evaluation.
    with imported.connect() as connection:
        transaction = connection.begin()
        connection.execute(sa.update(GeoPOIRecord).values(categories=["amenity:cafe"]))

        def session() -> Iterator[Session]:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                yield db

        previous = app.dependency_overrides[get_session]
        app.dependency_overrides[get_session] = session
        try:
            data = client.post(PATH, json=body()).json()
            assert data["comparison_ids"], data
            reverse = body()
            scoring = reverse["scoring"]
            assert isinstance(scoring, dict)
            scoring["competitor_mode"] = "separation"
            opposite = client.post(PATH, json=reverse).json()
            for result in data["evaluations"]:
                other = next(
                    r
                    for r in opposite["evaluations"]
                    if r["candidate_id"] == result["candidate_id"]
                )
                if result["score"] is not None:
                    assert result["score"] + other["score"] == pytest.approx(100)
        finally:
            app.dependency_overrides[get_session] = previous
            transaction.rollback()

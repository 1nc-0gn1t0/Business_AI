"""Synthetic, explicitly controlled topology; real Kazan verification is separate."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.bank.matching import digest
from app.db.models import GeoDatasetRecord, GeoPOIRecord, WalkEdgeRecord
from app.geo.provider import GeoImportError
from app.geo.schemas import Bounds
from app.geo.walk_import import import_graph, query, segments
from app.geo.walk_schemas import CatchmentRequest, WalkManifest
from app.geo.walking import catchment

pytestmark = pytest.mark.skipif(os.getenv("BA_RUN_DB_TESTS") != "1", reason="Requires PostGIS")


def topology(slug: str) -> tuple[WalkManifest, dict[str, Any]]:
    now = datetime(2026, 10, 23, tzinfo=UTC)
    points = {
        1: (49.12, 55.78),
        2: (49.122, 55.78),
        3: (49.122, 55.782),
        4: (49.12, 55.782),
        5: (49.121, 55.779),
        6: (49.121, 55.783),
        7: (49.123, 55.782),
    }
    elements: list[dict[str, Any]] = [
        {"type": "node", "id": i, "lon": p[0], "lat": p[1]} for i, p in points.items()
    ]
    # U-shaped detour and geometric crossing on a disconnected bridge (no shared node).
    elements += [
        {"type": "way", "id": 101, "nodes": [1, 2, 3, 4], "tags": {"highway": "footway"}},
        {
            "type": "way",
            "id": 102,
            "nodes": [5, 6],
            "tags": {"highway": "footway", "bridge": "yes", "layer": "1"},
        },
        {
            "type": "way",
            "id": 103,
            "nodes": [3, 7],
            "tags": {"highway": "footway", "oneway:foot": "yes"},
        },
    ]
    for e in elements:
        e.update(version=1, timestamp=now.isoformat())
    doc = {"osm3s": {"timestamp_osm_base": now.isoformat()}, "elements": elements}
    bbox = Bounds(west=49.10, south=55.76, east=49.14, north=55.80)
    manifest = WalkManifest(
        slug=slug,
        city="Synthetic test",
        bbox=bbox,
        source_url="https://example.invalid/synthetic-topology-not-osm",
        query=query(bbox),
        sha256=digest(doc),
        source_sha256=digest(doc),
        osm_base=now,
        fetched_at=now,
    )
    return manifest, doc


def seed(session: Session) -> tuple[str, WalkManifest, dict[str, Any]]:
    slug = "walk-test-" + uuid4().hex[:8]
    manifest, doc = topology(slug)
    dataset = GeoDatasetRecord(
        id=uuid4(),
        slug=slug,
        city=manifest.city,
        bbox=manifest.bbox.model_dump(),
        source_url=manifest.source_url,
        query="synthetic fixture",
        data_version="a" * 64,
        osm_base=manifest.osm_base,
        fetched_at=manifest.fetched_at,
        imported_at=manifest.fetched_at,
        active=True,
        poi_count=2,
        district_count=0,
        diagnostics={},
    )
    session.add(dataset)
    session.flush()
    for i, point in enumerate(((49.12, 55.782), (49.122, 55.78)), 1):
        session.add(
            GeoPOIRecord(
                dataset_id=dataset.id,
                osm_type="node",
                osm_id=i,
                osm_version=1,
                observed_at=manifest.osm_base,
                name="Synthetic test POI",
                categories=["amenity:cafe"],
                tags={},
                representation="osm_node",
                geom=f"SRID=4326;POINT({point[0]} {point[1]})",
            )
        )
    session.flush()
    return slug, manifest, doc


def test_import_topology_replay_geometry_network_detour_and_versions(
    migrated_database: tuple[Engine, UUID],
) -> None:
    engine, _ = migrated_database
    with Session(engine) as session, session.begin():
        slug, manifest, doc = seed(session)
        graph = import_graph(session, manifest, doc)
        assert graph.edge_count == 5 and graph.component_count == 2
        assert import_graph(session, manifest, doc) == graph
        assert (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(WalkEdgeRecord)
                .where(WalkEdgeRecord.graph_id == graph.id)
            )
            == 5
        )
        request = CatchmentRequest(longitude=49.12, latitude=55.78, distance_m=600, max_snap_m=0)
        result = catchment(session, slug, request)
        assert result.status == "ok", result
        assert result.source_component_nodes == 5 and result.on_largest_component
        boundary = catchment(session, slug, request.model_copy(update={"distance_m": 2000}))
        assert boundary.status == "partial" and not boundary.fully_covered
        assert result.reachable_poi_count == 2
        distant = next(p for p in result.pois.features if p.properties["osm_id"] == 1)
        assert (
            distant.properties["network_distance_m"]
            > distant.properties["straight_line_distance_m"] + 200
        )
        assert all(f.properties["edge_id"] != 4 for f in result.network.features)
        assert result.request_fingerprint == catchment(session, slug, request).request_fingerprint
        short = catchment(session, slug, request.model_copy(update={"distance_m": 250}))
        assert short.straight_line_poi_count == 2 and short.reachable_poi_count == 1
        assert short.no_route_in_loaded_graph_count >= 1
        assert catchment(
            session, slug, request.model_copy(update={"longitude": 49.101, "distance_m": 2000})
        ).status in {"no_network_access", "partial"}
        with pytest.raises(Exception) as error:
            catchment(session, slug, request.model_copy(update={"graph_version": "0" * 64}))
        assert getattr(error.value, "status_code", None) == 409


def test_missing_graph_partial_coverage_and_api(
    client: TestClient, migrated_database: tuple[Engine, UUID]
) -> None:
    engine, _ = migrated_database
    with Session(engine) as session, session.begin():
        slug, manifest, doc = seed(session)
        no_graph = catchment(session, slug, CatchmentRequest(longitude=49.12, latitude=55.78))
        assert no_graph.status == "graph_unavailable" and no_graph.network.features == ()
        import_graph(session, manifest, doc)
    url = f"/api/v1/geo/{slug}"
    graph = client.get(url + "/walking-graph")
    assert graph.status_code == 200
    body = {"longitude": 49.12, "latitude": 55.78, "distance_m": 500, "max_snap_m": 0}
    result = client.post(url + "/catchment", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["distance_method"].startswith("directed_osm_network")
    assert client.post(url + "/catchment", json={**body, "distance_m": 0}).status_code == 422
    assert (
        client.post(url + "/catchment", json={**body, "latitude": 55.9}).json()["status"]
        == "outside_coverage"
    )
    assert (
        client.post(url + "/catchment", json={**body, "data_version": "0" * 64}).status_code == 409
    )
    ranking = {
        "ranking": {
            "candidates": {
                "profile": {
                    "conversation_id": str(uuid4()),
                    "city": "Synthetic test",
                    "category": "кофейня",
                    "confirmation_state": "confirmed",
                },
                "cell_size_m": 250,
                "min_separation_m": 0,
                "limit": 3,
            },
            "scoring": {
                "radius_m": 50,
                "competitor_mode": "cluster",
                "weights": {
                    "transit": 0,
                    "infrastructure": 0,
                    "complementary": 0,
                    "competitors": 1,
                },
            },
        },
        "max_snap_m": 30,
    }
    compared = client.post(url + "/walking-rankings", json=ranking)
    assert compared.status_code == 200, compared.text
    assert (
        compared.json()["baseline"]["algorithm_version"]
        != compared.json()["network"]["algorithm_version"]
    )
    assert all(
        e["raw"]["distance_method"] == "walking_network_with_connectors"
        for e in compared.json()["network"]["evaluations"]
    )


def test_barriers_missing_nodes_and_foot_restrictions() -> None:
    manifest, doc = topology("test-topology")
    doc["elements"][1]["tags"] = {"barrier": "wall"}
    built, diagnostics = segments(manifest, doc)
    assert diagnostics["blocked_segments"] == 2
    assert not any(e["u"] == 2 or e["v"] == 2 for e in built)
    manifest, doc = topology("test-topology")
    doc["elements"].pop(0)
    with pytest.raises(GeoImportError):
        segments(manifest, doc)
    manifest, doc = topology("test-topology")
    doc["elements"].append(
        {
            "type": "relation",
            "id": 999,
            "version": 1,
            "timestamp": manifest.osm_base.isoformat(),
            "tags": {"restriction:foot": "no_straight_on"},
            "members": [{"type": "way", "ref": 101, "role": "from"}],
        }
    )
    built, diagnostics = segments(manifest, doc)
    assert diagnostics["restricted_relations"] == 1
    assert not any(e["way_id"] == 101 for e in built)


def test_old_or_empty_import_preserves_active(migrated_database: tuple[Engine, UUID]) -> None:
    engine, _ = migrated_database
    with Session(engine) as session, session.begin():
        slug, manifest, doc = seed(session)
        graph = import_graph(session, manifest, doc)
        old = manifest.model_copy(
            update={"osm_base": manifest.osm_base - timedelta(days=1), "sha256": "b" * 64}
        )
        with pytest.raises(GeoImportError):
            import_graph(session, old, doc)
        empty = {**doc, "elements": []}
        with pytest.raises(GeoImportError):
            import_graph(session, manifest.model_copy(update={"sha256": "c" * 64}), empty)
        assert (
            catchment(session, slug, CatchmentRequest(longitude=49.12, latitude=55.78)).graph
            == graph
        )

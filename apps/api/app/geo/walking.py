from collections import Counter
from time import perf_counter
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.bank.matching import digest
from app.db.models import WalkGraphRecord
from app.geo.schemas import Bounds
from app.geo.service import GeoData
from app.geo.walk_graph import (
    ALGORITHM_VERSION,
    Edge,
    Snap,
    reachable_intervals,
    route_distance,
    traverse,
)
from app.geo.walk_schemas import CatchmentRequest, CatchmentResult, WalkGraphView

LIMITATIONS = (
    "OSM network and POI mapping may be incomplete/outdated; "
    "no route is not proof of physical inaccessibility.",
    "Directed OSM-node topology only; geometric intersections without shared nodes never connect.",
    "Origin and POI connectors are straight-line modelling assumptions, not verified entrances "
    "or paths across barriers; max_snap_m bounds them.",
    "Only ground-level non-bridge/non-tunnel edges accept connectors. "
    "Bridges and tunnels can be traversed through real shared nodes.",
    "Reachable segments are a network visualization, not an exact walkable-area polygon "
    "or measured pedestrian traffic.",
    "Costs are metres along WGS84 edges plus connectors; not walking time, "
    "wheelchair accessibility, demand or profitability.",
    "Conditional access and foot turn restrictions are conservatively excluded; "
    "general vehicle one-way does not imply foot one-way.",
    "POI centers may not be entrances. Counts describe features, not people or businesses.",
)
POINT = "ST_SetSRID(ST_MakePoint(:lon,:lat),4326)"
SNAPPABLE = (
    "coalesce(e.tags->>'layer','0')='0' "
    "AND coalesce(e.tags->>'bridge','no') IN ('no','false','0') "
    "AND coalesce(e.tags->>'tunnel','no') IN ('no','false','0')"
)


def graph_for(session: Session, slug: str, version: str | None = None) -> WalkGraphView | None:
    statement = sa.select(WalkGraphRecord).where(WalkGraphRecord.slug == slug)
    statement = (
        statement.where(WalkGraphRecord.graph_version == version)
        if version
        else statement.where(WalkGraphRecord.active)
    )
    row = session.scalar(statement)
    if row is None and version:
        raise HTTPException(409, detail={"code": "walking_graph_version_not_found"})
    return WalkGraphView.model_validate(row.document) if row else None


def catchment(session: Session, slug: str, request: CatchmentRequest) -> CatchmentResult:
    started = perf_counter()
    dataset = GeoData(session).dataset(slug, request.data_version)
    graph = graph_for(session, slug, request.graph_version)
    base: dict[str, Any] = {
        "request_snapshot": request,
        "algorithm_version": ALGORITHM_VERSION,
        "request_fingerprint": digest(
            {
                "request": request.model_dump(mode="json"),
                "poi": dataset.data_version,
                "graph": graph.graph_version if graph else None,
                "algorithm": ALGORITHM_VERSION,
            }
        ),
        "poi_data_version": dataset.data_version,
        "graph": graph,
        "limitations": LIMITATIONS,
    }

    def result(status: str, reasons: list[str], **values: Any) -> CatchmentResult:
        return CatchmentResult.model_validate(
            {
                **base,
                "status": status,
                "reasons": reasons,
                "runtime_ms": round((perf_counter() - started) * 1000, 3),
                **values,
            }
        )

    if graph is None:
        return result("graph_unavailable", ["walking_graph_not_imported_no_straight_line_fallback"])
    bbox = graph.manifest.bbox
    if not bbox.contains(request.longitude, request.latitude):
        return result("outside_coverage", ["origin_outside_graph_coverage"])
    params: dict[str, Any] = {
        "lon": request.longitude,
        "lat": request.latitude,
        "graph_id": graph.id,
        "radius": request.distance_m + request.max_snap_m + 5,
        "budget": request.distance_m,
        "snap": request.max_snap_m + 0.001,
        "srid": graph.metric_crs,
        "dataset_id": dataset.id,
        **bbox.model_dump(),
    }
    poi_bounds = Bounds.model_validate(dataset.bbox)
    coverage = Bounds(
        west=max(bbox.west, poi_bounds.west),
        south=max(bbox.south, poi_bounds.south),
        east=min(bbox.east, poi_bounds.east),
        north=min(bbox.north, poi_bounds.north),
    )
    margin = float(
        session.scalar(
            sa.text(
                f"SELECT ST_Distance({POINT}::geography,ST_Segmentize(ST_Boundary("
                "ST_MakeEnvelope(:west,:south,:east,:north,4326)),0.001)::geography)"
            ),
            params | coverage.model_dump(),
        )
        or 0
    )
    fully = margin >= request.distance_m + request.max_snap_m + 1
    base.update(coverage_margin_m=round(margin, 3), fully_covered=fully)
    rows = (
        session.execute(
            sa.text(f"""SELECT edge_id,u,v,forward,backward,length_m,
                ST_AsGeoJSON(geom)::json coordinates
    FROM walk_edges WHERE graph_id=:graph_id
    AND ST_DWithin(geom::geography,{POINT}::geography,:radius)
    ORDER BY edge_id LIMIT 20001"""),
            params,
        )
        .mappings()
        .all()
    )
    if len(rows) > 20000:
        return result("resource_limit", ["local_graph_exceeds_20000_edges_reduce_distance"])
    edges = {
        r["edge_id"]: Edge(
            r["edge_id"],
            r["u"],
            r["v"],
            r["length_m"],
            r["forward"],
            r["backward"],
            (
                (r["coordinates"]["coordinates"][0][0], r["coordinates"]["coordinates"][0][1]),
                (r["coordinates"]["coordinates"][1][0], r["coordinates"]["coordinates"][1][1]),
            ),
        )
        for r in rows
    }
    base["loaded_edges"] = len(edges)
    snap_row = (
        session.execute(
            sa.text(f"""SELECT e.edge_id,e.tags,
        ST_Distance(e.geom::geography,{POINT}::geography) connector,
        ST_LineLocatePoint(ST_Transform(e.geom,:srid),ST_Transform({POINT},:srid)) fraction
        FROM walk_edges e WHERE e.graph_id=:graph_id AND {SNAPPABLE}
        AND ST_DWithin(e.geom::geography,{POINT}::geography,:snap)
        ORDER BY connector,e.edge_id LIMIT 1"""),
            params,
        )
        .mappings()
        .first()
    )
    if not snap_row or snap_row["edge_id"] not in edges:
        return result(
            "no_network_access",
            ["no_eligible_ground_level_edge_within_snap_limit_not_proof_of_inaccessibility"],
        )
    start = Snap(edges[snap_row["edge_id"]], snap_row["fraction"], snap_row["connector"])
    distances = traverse(list(edges.values()), start, request.distance_m)
    base.update(source_snap_m=round(start.connector, 3), visited_nodes=len(distances))
    component_nodes = snap_row["tags"].get("component_nodes")
    largest = snap_row["tags"].get("on_largest_component") is True
    base.update(source_component_nodes=component_nodes, on_largest_component=largest)
    features = []
    for e in edges.values():
        for low, high in reachable_intervals(e, start, distances, request.distance_m):
            a, b = e.coordinates
            coordinates = [
                [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t] for t in (low, high)
            ]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                    "properties": {
                        "edge_id": e.id,
                        "reachable_length_m": round((high - low) * e.length, 3),
                    },
                }
            )
    # Nearest single eligible edge, including disconnected components, avoids attaching
    # a POI to whichever distant reachable component makes the result look better.
    poi_rows = (
        session.execute(
            sa.text(f"""SELECT p.osm_type,p.osm_id,p.name,p.categories,p.representation,
      ST_AsGeoJSON(p.geom)::json geometry,
      ST_Distance(p.geom::geography,{POINT}::geography) straight_m,
      s.edge_id,s.connector,s.fraction
      FROM geo_pois p LEFT JOIN LATERAL (
        SELECT e.edge_id, ST_Distance(e.geom::geography,p.geom::geography) connector,
          ST_LineLocatePoint(ST_Transform(e.geom,:srid),ST_Transform(p.geom,:srid)) fraction
        FROM walk_edges e WHERE e.graph_id=:graph_id AND {SNAPPABLE}
        AND ST_DWithin(e.geom::geography,p.geom::geography,:snap)
        ORDER BY connector,e.edge_id LIMIT 1
      ) s ON true WHERE p.dataset_id=:dataset_id
      AND ST_DWithin(p.geom::geography,{POINT}::geography,:budget)
      ORDER BY p.osm_type,p.osm_id LIMIT 5001"""),
            params,
        )
        .mappings()
        .all()
    )
    if len(poi_rows) > 5000:
        return result("resource_limit", ["more_than_5000_nearby_pois_reduce_distance"])
    counts: Counter[str] = Counter()
    poi_features = []
    unsnapped = no_route = 0
    for row in poi_rows:
        if row["edge_id"] not in edges:
            unsnapped += 1
            continue
        cost = route_distance(
            start, Snap(edges[row["edge_id"]], row["fraction"], row["connector"]), distances
        )
        if cost is None:
            no_route += 1
            continue
        if cost > request.distance_m + 1e-6:
            continue
        counts.update(row["categories"])
        poi_features.append(
            {
                "type": "Feature",
                "id": f"{row['osm_type']}/{row['osm_id']}",
                "geometry": row["geometry"],
                "properties": {
                    "osm_type": row["osm_type"],
                    "osm_id": row["osm_id"],
                    "name": row["name"],
                    "categories": row["categories"],
                    "network_distance_m": round(cost, 3),
                    "straight_line_distance_m": round(row["straight_m"], 3),
                    "connector_m": round(row["connector"], 3),
                    "representation": row["representation"],
                },
            }
        )
    reasons = ["bounded_network_with_modelled_connectors_not_verified_entrances"]
    if not largest:
        reasons.append("origin_on_nonprincipal_or_unknown_component_quality_limited")
    if not fully:
        reasons.append("observation_budget_reaches_graph_or_poi_boundary_counts_are_lower_bounds")
    return result(
        "ok" if fully and largest else "partial",
        reasons,
        network={"features": features},
        pois={"features": poi_features},
        category_counts=dict(sorted(counts.items())),
        reachable_poi_count=len(poi_features),
        straight_line_poi_count=len(poi_rows),
        unsnapped_poi_count=unsnapped,
        no_route_in_loaded_graph_count=no_route,
    )

import json
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import GeoDatasetRecord
from app.geo.provider import GeoImportError
from app.geo.schemas import SnapshotManifest, valid_coordinate

TAG_KEYS = {
    "name",
    "name:ru",
    "amenity",
    "shop",
    "highway",
    "brand",
    "operator",
    "addr:street",
    "addr:housenumber",
    "wheelchair",
    "opening_hours",
}

POI_INSERT = sa.text("""
    INSERT INTO geo_pois
      (dataset_id, osm_type, osm_id, osm_version, observed_at, name, categories,
       tags, representation, geom)
    VALUES (:dataset_id, :osm_type, :osm_id, :osm_version, :observed_at, :name,
      :categories, CAST(:tags AS jsonb), :representation,
      ST_SetSRID(ST_MakePoint(:lon, :lat),4326))
""")

DISTRICT_INSERT = sa.text("""
    WITH lines AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:lines),4326) AS geom),
    area AS (SELECT ST_Multi(ST_BuildArea(geom)) AS geom FROM lines
             WHERE ST_IsClosed(ST_LineMerge(geom)))
    INSERT INTO geo_districts
      (dataset_id, osm_id, osm_version, observed_at, name, admin_level, geom)
    SELECT :dataset_id, :osm_id, :osm_version, :observed_at, :name, :admin_level, geom
    FROM area WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom) AND ST_IsValid(geom)
      AND GeometryType(geom) = 'MULTIPOLYGON'
    RETURNING osm_id
""")


def _identity(element: dict[str, Any], manifest: SnapshotManifest) -> dict[str, Any]:
    if element.get("type") not in {"node", "way", "relation"}:
        raise ValueError("unsupported element")
    if (
        type(element.get("id")) is not int
        or element["id"] <= 0
        or type(element.get("version")) is not int
        or element["version"] <= 0
    ):
        raise ValueError("missing identity/version")
    observed = datetime.fromisoformat(element["timestamp"].replace("Z", "+00:00"))
    if observed.tzinfo is None or observed > manifest.osm_base:
        raise ValueError("missing/invalid timestamp")
    return {
        "osm_type": element["type"],
        "osm_id": element["id"],
        "osm_version": element["version"],
        "observed_at": observed,
    }


def _lines(element: dict[str, Any]) -> str:
    lines = []
    for member in element.get("members", []):
        if member.get("type") == "relation":
            raise ValueError("Nested boundary relations require a fuller import format")
        if member.get("type") != "way":
            continue
        if member.get("role", "") not in {"outer", "inner", ""}:
            raise ValueError("unsupported way role")
        coordinates = [[float(point["lon"]), float(point["lat"])] for point in member["geometry"]]
        if len(coordinates) < 2 or not all(valid_coordinate(*point) for point in coordinates):
            raise ValueError("incomplete boundary geometry")
        lines.append(coordinates)
    if not lines:
        raise ValueError("missing boundary ways")
    return json.dumps({"type": "MultiLineString", "coordinates": lines})


def import_snapshot(
    session: Session,
    manifest: SnapshotManifest,
    document: dict[str, Any],
    *,
    allow_empty: bool = False,
    checkpoint: Callable[[], None] | None = None,
) -> GeoDatasetRecord:
    """Caller owns transaction. Publish complete snapshot atomically; preserve old versions."""
    session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": "business-ai:osm:" + manifest.slug},
    )
    current = session.scalar(
        sa.select(GeoDatasetRecord).where(
            GeoDatasetRecord.slug == manifest.slug, GeoDatasetRecord.active
        )
    )
    previous = session.scalar(
        sa.select(GeoDatasetRecord).where(
            GeoDatasetRecord.slug == manifest.slug, GeoDatasetRecord.data_version == manifest.sha256
        )
    )
    if current and (current.bbox != manifest.bbox.model_dump() or current.query != manifest.query):
        raise GeoImportError("Dataset coverage/query changed; choose another slug")
    if current and manifest.osm_base < current.osm_base:
        raise GeoImportError("Older OSM snapshot cannot replace current data")
    if previous:
        if (
            previous.source_url != manifest.source_url
            or previous.bbox != manifest.bbox.model_dump()
        ):
            raise GeoImportError("Snapshot metadata changed")
        if not previous.active:
            raise GeoImportError("Historical snapshot cannot be reactivated")
        return previous
    record = GeoDatasetRecord(
        id=uuid4(),
        slug=manifest.slug,
        city=manifest.city,
        bbox=manifest.bbox.model_dump(),
        source_url=manifest.source_url,
        query=manifest.query,
        data_version=manifest.sha256,
        osm_base=manifest.osm_base,
        fetched_at=manifest.fetched_at,
        imported_at=datetime.now(UTC),
        active=False,
        diagnostics={},
    )
    session.add(record)
    session.flush()
    counts: Counter[str] = Counter()
    elements: dict[tuple[str, int], dict[str, Any]] = {}
    for index, item in enumerate(document["elements"]):
        if checkpoint and index % 250 == 0:
            checkpoint()
        if not isinstance(item, dict):
            counts["invalid_element"] += 1
            continue
        try:
            identity = _identity(item, manifest)
        except (ValueError, KeyError, TypeError, AttributeError):
            counts["invalid_metadata"] += 1
            continue
        key = (identity["osm_type"], identity["osm_id"])
        if key in elements and elements[key]["version"] != item["version"]:
            raise GeoImportError("Conflicting OSM versions in one snapshot")
        elements[key] = elements.get(key, {}) | item
    batch: list[dict[str, Any]] = []
    for index, item in enumerate(elements.values()):
        if checkpoint and index % 250 == 0:
            checkpoint()
        identity = _identity(item, manifest)
        tags = item.get("tags", {})
        if not isinstance(tags, dict) or not all(isinstance(v, str) for v in tags.values()):
            counts["invalid_tags"] += 1
            continue
        name = tags.get("name:ru") or tags.get("name") or None
        if tags.get("boundary") == "administrative":
            try:
                if item["type"] != "relation" or tags["admin_level"] not in {"8", "9", "10"}:
                    raise ValueError
                lines = _lines(item)
            except (ValueError, KeyError, TypeError, AttributeError):
                counts["incomplete_boundary"] += 1
                continue
            params = identity | {
                "dataset_id": record.id,
                "name": name,
                "admin_level": int(tags["admin_level"]),
                "lines": lines,
            }
            if session.scalar(DISTRICT_INSERT, params) is None:
                counts["invalid_boundary"] += 1
            else:
                counts["districts"] += 1
            continue
        categories = [f"{key}:{tags[key]}" for key in ("amenity", "shop") if tags.get(key)]
        if tags.get("highway") == "bus_stop":
            categories.append("highway:bus_stop")
        if not categories:
            counts["unselected_tags"] += 1
            continue
        try:
            point = item if item["type"] == "node" else item["center"]
            lon, lat = float(point["lon"]), float(point["lat"])
            if not valid_coordinate(lon, lat):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            counts["missing_location"] += 1
            continue
        if not manifest.bbox.contains(lon, lat):
            counts["center_outside_bbox"] += 1
            continue
        if not name:
            counts["unnamed_pois"] += 1
        batch.append(
            identity
            | {
                "dataset_id": record.id,
                "lon": lon,
                "lat": lat,
                "name": name,
                "categories": categories,
                "tags": json.dumps({key: value for key, value in tags.items() if key in TAG_KEYS}),
                "representation": "osm_node" if item["type"] == "node" else "osm_bbox_center",
            }
        )
        counts["pois"] += 1
        if len(batch) == 500:
            session.execute(POI_INSERT, batch)
            batch.clear()
    if batch:
        session.execute(POI_INSERT, batch)
    if counts["pois"] == 0 and not allow_empty:
        raise GeoImportError("Empty POI snapshot rejected; use --allow-empty only after inspection")
    if checkpoint:
        checkpoint()
    if current:
        current.active = False
        session.flush()
    record.poi_count = counts["pois"]
    record.district_count = counts["districts"]
    record.diagnostics = dict(counts)
    record.active = True
    session.flush()
    session.execute(sa.text("ANALYZE geo_pois"))
    session.execute(sa.text("ANALYZE geo_districts"))
    return record

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import GeoDatasetRecord
from app.geo.schemas import SpatialQuery

LIMITATIONS = [
    "OSM coverage and tags may be incomplete or outdated; an empty result is not proof of absence.",
    "Only amenity, shop and highway=bus_stop objects inside the saved bbox are included.",
    "Way/relation POI use OSM bounding-box centers, not entrances or building footprints.",
    "OSM identities are not deduplicated businesses; distances are straight-line, not routes.",
    "No measured traffic, demand, rent, revenue or bank-product conditions are provided.",
    "Administrative polygons may extend outside POI coverage; missing boundaries are not inferred.",
    "Overpass boundary bbox selection uses member nodes, so containing districts may be absent.",
]


class GeoData:
    def __init__(self, session: Session):
        self.session = session

    def dataset(self, slug: str, version: str | None = None) -> GeoDatasetRecord:
        record = self.session.scalar(
            sa.select(GeoDatasetRecord).where(
                GeoDatasetRecord.slug == slug, GeoDatasetRecord.active
            )
        )
        if record is None:
            raise HTTPException(404, detail={"code": "geo_dataset_not_found"})
        if version and version != record.data_version:
            raise HTTPException(
                409, detail={"code": "geo_dataset_changed", "data_version": record.data_version}
            )
        return record

    @staticmethod
    def metadata(record: GeoDatasetRecord) -> dict[str, Any]:
        age = max(0, (datetime.now(UTC) - record.osm_base).days)
        return {
            "slug": record.slug,
            "city": record.city,
            "bbox": record.bbox,
            "data_version": record.data_version,
            "origin": "open_data",
            "source_name": "OpenStreetMap via Overpass API",
            "source_url": record.source_url,
            "license": "ODbL-1.0",
            "license_url": "https://www.openstreetmap.org/copyright",
            "attribution": "© OpenStreetMap contributors",
            "osm_base": record.osm_base,
            "fetched_at": record.fetched_at,
            "imported_at": record.imported_at,
            "age_days": age,
            "stale": age > 30,
            "stale_after_days": 30,
            "poi_count": record.poi_count,
            "district_count": record.district_count,
            "diagnostics": record.diagnostics,
            "limitations": LIMITATIONS,
        }

    def datasets(self) -> list[dict[str, Any]]:
        return [
            self.metadata(row)
            for row in self.session.scalars(
                sa.select(GeoDatasetRecord)
                .where(GeoDatasetRecord.active)
                .order_by(GeoDatasetRecord.slug)
            )
        ]

    def pois(self, slug: str, query: SpatialQuery) -> dict[str, Any]:
        record = self.dataset(slug, query.data_version)
        params: dict[str, Any] = {
            "dataset_id": record.id,
            "limit": query.limit + 1,
            "offset": query.offset,
        }
        clauses = ["p.dataset_id = :dataset_id"]
        distance = "NULL::double precision"
        if query.bbox:
            clauses.append("p.geom && ST_MakeEnvelope(:west,:south,:east,:north,4326)")
            params |= query.bbox.model_dump()
        if query.radius_m is not None:
            point = "ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326)::geography"
            clauses.append(f"ST_DWithin(p.geom::geography,{point},:radius_m)")
            distance = f"ST_Distance(p.geom::geography,{point})"
            params |= {
                "longitude": query.longitude,
                "latitude": query.latitude,
                "radius_m": query.radius_m,
            }
        if query.category:
            clauses.append("p.categories @> ARRAY[CAST(:category AS text)]")
            params["category"] = query.category
        if query.district_id:
            if (
                self.session.scalar(
                    sa.text("""
                SELECT osm_id FROM geo_districts WHERE dataset_id=:dataset_id AND osm_id=:id
            """),
                    {"dataset_id": record.id, "id": query.district_id},
                )
                is None
            ):
                raise HTTPException(404, detail={"code": "geo_district_not_found"})
            clauses.append("""EXISTS (SELECT 1 FROM geo_districts d
                WHERE d.dataset_id=p.dataset_id AND d.osm_id=:district_id
                AND ST_Covers(d.geom,p.geom))""")
            params["district_id"] = query.district_id
        where = " AND ".join(clauses)
        # Every interpolated fragment above is static SQL, all request data is bound.
        rows = (
            self.session.execute(
                sa.text(f"""
            SELECT p.osm_type, p.osm_id, p.osm_version, p.observed_at, p.name,
              p.categories, p.tags, p.representation, ST_AsGeoJSON(p.geom)::jsonb AS geometry,
              {distance} AS distance_m FROM geo_pois p WHERE {where}
            ORDER BY distance_m NULLS LAST, p.osm_type, p.osm_id LIMIT :limit OFFSET :offset
        """),
                params,
            )
            .mappings()
            .all()
        )
        features = []
        for row in rows[: query.limit]:
            features.append(
                {
                    "type": "Feature",
                    "id": f"{row['osm_type']}/{row['osm_id']}",
                    "geometry": row["geometry"],
                    "properties": {
                        key: row[key]
                        for key in (
                            "osm_type",
                            "osm_id",
                            "osm_version",
                            "observed_at",
                            "name",
                            "categories",
                            "tags",
                            "representation",
                            "distance_m",
                        )
                    },
                }
            )
        return {
            "type": "FeatureCollection",
            "features": features,
            "dataset": self.metadata(record),
            "returned_count": len(features),
            "next_offset": query.offset + query.limit if len(rows) > query.limit else None,
            "coverage": "saved_bbox_only",
        }

    def districts(self, slug: str, version: str | None) -> dict[str, Any]:
        record = self.dataset(slug, version)
        rows = (
            self.session.execute(
                sa.text("""
            SELECT osm_id, osm_version, observed_at, name, admin_level,
              ST_AsGeoJSON(geom)::jsonb AS geometry FROM geo_districts
            WHERE dataset_id=:id ORDER BY admin_level, osm_id LIMIT 101
        """),
                {"id": record.id},
            )
            .mappings()
            .all()
        )
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": f"relation/{row['osm_id']}",
                    "geometry": row["geometry"],
                    "properties": {
                        key: row[key]
                        for key in ("osm_id", "osm_version", "observed_at", "name", "admin_level")
                    },
                }
                for row in rows[:100]
            ],
            "truncated": len(rows) > 100,
            "dataset": self.metadata(record),
        }

    def categories(self, slug: str) -> dict[str, Any]:
        record = self.dataset(slug)
        rows = (
            self.session.execute(
                sa.text("""
            SELECT category, count(*) AS mapped_features FROM geo_pois,
              LATERAL unnest(categories) AS category
            WHERE dataset_id=:id GROUP BY category ORDER BY category
        """),
                {"id": record.id},
            )
            .mappings()
            .all()
        )
        return {"dataset": self.metadata(record), "categories": [dict(row) for row in rows]}

import hashlib
import json
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import GeoDistrictRecord
from app.geo.candidate_policy import (
    ALGORITHM_VERSION,
    NOT_EVALUATED,
    POLICIES,
    POLICY_VERSION,
    business_key,
    city_key,
    disperse,
    fingerprint,
    metric_srid,
    normalize,
)
from app.geo.candidate_schemas import CandidateCollection, CandidateRequest
from app.geo.schemas import Bounds
from app.geo.service import GeoData

MAX_GRID_CELLS = 12000

REGION_SQL = """
WITH coverage AS (SELECT ST_MakeEnvelope(:west,:south,:east,:north,4326) g),
requested AS (
 SELECT CASE WHEN CAST(:search AS text) IS NULL THEN g
 ELSE ST_GeomFromGeoJSON(CAST(:search AS text)) END g FROM coverage
), included AS (
 SELECT CASE WHEN cardinality(CAST(:included AS bigint[])) = 0 THEN r.g
 ELSE (SELECT CASE WHEN CAST(:search AS text) IS NULL THEN ST_UnaryUnion(ST_Collect(d.geom))
 ELSE ST_Intersection(r.g,ST_UnaryUnion(ST_Collect(d.geom))) END
 FROM geo_districts d WHERE d.dataset_id=:dataset_id
 AND d.osm_id=ANY(CAST(:included AS bigint[]))) END g FROM requested r
), excluded AS (
 SELECT CASE WHEN cardinality(CAST(:excluded AS bigint[])) = 0 THEN g
 ELSE ST_Difference(g, (SELECT ST_UnaryUnion(ST_Collect(d.geom))
 FROM geo_districts d WHERE d.dataset_id=:dataset_id
 AND d.osm_id=ANY(CAST(:excluded AS bigint[])))) END g FROM included
), clipped AS (
 SELECT ST_Multi(ST_CollectionExtract(ST_Intersection(e.g,c.g),3)) g,
 NOT ST_Covers(c.g,e.g) partial FROM excluded e CROSS JOIN coverage c
)
SELECT encode(ST_AsEWKB(g),'hex') region, partial, ST_IsEmpty(g) empty,
 (ceil((ST_XMax(ST_Transform(g,:srid))-ST_XMin(ST_Transform(g,:srid)))/:size)+2)
 *(ceil((ST_YMax(ST_Transform(g,:srid))-ST_YMin(ST_Transform(g,:srid)))/:size)+2) grid_count
FROM clipped
"""

CELLS_SQL = """
WITH region AS (SELECT ST_GeomFromEWKB(decode(:region,'hex')) g),
metric AS (SELECT ST_Transform(g,:srid) g FROM region),
grid AS (
 SELECT s.i,s.j,ST_Intersection(s.geom,m.g) g
 FROM metric m CROSS JOIN LATERAL ST_SquareGrid(:size,m.g) s
 WHERE ST_Intersects(s.geom,m.g)
), clipped AS MATERIALIZED (
 SELECT c.i,c.j, ST_Multi(ST_CollectionExtract(ST_Intersection(
 ST_Transform(ST_Buffer(c.g,-0.02),4326),r.g),3)) g
 FROM grid c CROSS JOIN region r
 WHERE ST_Area(c.g)>=:min_area
), valid AS MATERIALIZED (
 SELECT i,j,g,ST_PointOnSurface(g) point,ST_Area(ST_Transform(g,:srid)) area
 FROM clipped WHERE NOT ST_IsEmpty(g) AND ST_IsValid(g)
), observed AS (
 SELECT v.*,a.anchor,req.evidence,req.passed FROM valid v
 CROSS JOIN LATERAL (
  SELECT jsonb_build_object('type','Feature','id',p.osm_type||'/'||p.osm_id,
   'geometry',ST_AsGeoJSON(p.geom,15)::jsonb,
   'properties',jsonb_build_object('osm_type',p.osm_type,'osm_id',p.osm_id,
   'osm_version',p.osm_version,'observed_at',p.observed_at,'name',p.name,
   'categories',p.categories,'tags',p.tags,'representation',p.representation,
   'distance_m',ST_Distance(p.geom::geography,v.point::geography))) anchor
  FROM geo_pois p WHERE p.dataset_id=:dataset_id
   AND p.categories && CAST(:categories AS text[]) AND p.geom && v.g
   AND ST_Covers(v.g,p.geom)
  ORDER BY ST_Distance(p.geom::geography,v.point::geography),p.osm_type,p.osm_id LIMIT 1
 ) a
 CROSS JOIN LATERAL (
  SELECT coalesce(jsonb_agg(jsonb_build_object('requirement',q.value,
    'mapped_count',n.count) ORDER BY q.ordinality),'[]'::jsonb) evidence,
   coalesce(bool_and(n.count >= (q.value->>'min_count')::int),true) passed
  FROM jsonb_array_elements(CAST(:requirements AS jsonb)) WITH ORDINALITY q(value,ordinality)
  CROSS JOIN LATERAL (SELECT count(*) count FROM geo_pois p
   WHERE p.dataset_id=:dataset_id
    AND p.categories @> ARRAY[q.value->>'category']
    AND ST_DWithin(p.geom::geography,v.point::geography,
      (q.value->>'max_distance_m')::double precision)) n
 ) req WHERE v.area>=:min_area
)
SELECT i,j,ST_X(ST_Transform(point,:srid)) x,ST_Y(ST_Transform(point,:srid)) y,
 ST_AsGeoJSON(g,15)::jsonb geometry,ST_AsGeoJSON(point,15)::jsonb point,
 area,anchor,evidence FROM observed WHERE passed ORDER BY i,j
"""


def generate(session: Session, slug: str, request: CandidateRequest) -> CandidateCollection:
    data = GeoData(session)
    record = data.dataset(slug, request.data_version)
    bounds = Bounds.model_validate(record.bbox)
    try:
        srid = metric_srid(bounds)
    except ValueError:
        raise HTTPException(422, detail={"code": "unsupported_metric_extent"}) from None
    digest = fingerprint(request, record.data_version, srid)
    runtime = session.scalar(sa.text("SELECT PostGIS_Full_Version()"))
    base: dict[str, Any] = {
        "dataset": data.metadata(record),
        "profile_snapshot": request.profile,
        "request_snapshot": request.model_copy(update={"data_version": record.data_version}),
        "algorithm_version": ALGORITHM_VERSION,
        "policy_version": POLICY_VERSION,
        "request_fingerprint": digest,
        "metric_srid": srid,
        "spatial_runtime": runtime,
        "requested_count": request.limit,
        "not_evaluated": NOT_EVALUATED,
    }

    def empty(status: str, reason: str) -> CandidateCollection:
        return CandidateCollection.model_validate(base | {"status": status, "reasons": [reason]})

    profile = request.profile
    if not profile.city or not profile.category:
        return empty("insufficient_data", "profile_city_and_category_required")
    if city_key(profile.city) != city_key(record.city):
        return empty("insufficient_data", "profile_city_differs_from_dataset")
    categories = POLICIES.get(business_key(profile.category))
    if categories is None:
        return empty("insufficient_data", "unsupported_business_category")
    bindings = {r.profile_constraint for r in request.requirements}
    if set(profile.preferences.constraints) - bindings:
        return empty("needs_constraints", "unmapped_profile_constraints")

    districts = list(
        session.scalars(
            sa.select(GeoDistrictRecord).where(GeoDistrictRecord.dataset_id == record.id)
        )
    )
    known = {d.osm_id for d in districts}
    included = set(request.district_ids)
    if not (included | set(request.excluded_district_ids)) <= known:
        return empty("insufficient_data", "district_not_in_dataset")
    preferred: set[int] = set()
    for name in profile.preferences.preferred_districts:
        matches = [d.osm_id for d in districts if d.name and normalize(d.name) == normalize(name)]
        if len(matches) != 1:
            return empty("insufficient_data", "preferred_district_missing_or_ambiguous")
        preferred.add(matches[0])
    if preferred:
        if included and not included.intersection(preferred):
            return empty("no_candidates", "district_constraints_disjoint")
        included = included.intersection(preferred) if included else preferred

    search = request.search_bbox
    search_geo = (
        None
        if search is None
        else json.dumps(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [search.west, search.south],
                        [search.east, search.south],
                        [search.east, search.north],
                        [search.west, search.north],
                        [search.west, search.south],
                    ]
                ],
            }
        )
    )
    params: dict[str, Any] = bounds.model_dump() | {
        "dataset_id": record.id,
        "srid": srid,
        "size": request.cell_size_m,
        "search": search_geo,
        "included": sorted(included),
        "excluded": list(request.excluded_district_ids),
    }
    region = session.execute(sa.text(REGION_SQL), params).mappings().one()
    if region["empty"]:
        return empty("no_candidates", "empty_covered_region")
    if region["grid_count"] > MAX_GRID_CELLS:
        raise HTTPException(
            422, detail={"code": "candidate_grid_too_large", "max_cells": MAX_GRID_CELLS}
        )
    params |= {
        "region": region["region"],
        "min_area": request.cell_size_m**2 * 0.25,
        "categories": list(categories),
        "requirements": json.dumps([r.model_dump() for r in request.requirements]),
    }
    rows = [dict(row) for row in session.execute(sa.text(CELLS_SQL), params).mappings()]
    selected = disperse(rows, request.limit, request.min_separation_m)
    features = []
    for row in selected:
        identity = hashlib.sha256(f"{digest}:{row['i']}:{row['j']}".encode()).hexdigest()
        features.append(
            {
                "id": identity,
                "geometry": row["geometry"],
                "properties": {
                    "grid_i": row["i"],
                    "grid_j": row["j"],
                    "area_m2": row["area"],
                    "representative_point": row["point"],
                    "anchor": row["anchor"],
                    "requirements": row["evidence"],
                },
            }
        )
    reasons = ["saved_bbox_only", "geographic_dispersion_not_ranking"]
    if region["partial"]:
        reasons.append("requested_region_clipped_to_coverage")
    if len(features) < request.limit:
        reasons.append("insufficient_observed_cells_or_separation")
    status = (
        "no_candidates"
        if not features
        else ("partial" if region["partial"] or len(features) < request.limit else "ok")
    )
    return CandidateCollection.model_validate(
        base
        | {
            "features": features,
            "status": status,
            "reasons": reasons,
            "eligible_count": len(rows),
        }
    )

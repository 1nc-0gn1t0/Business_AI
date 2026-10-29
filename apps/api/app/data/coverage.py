"""Bounded metadata reads and deterministic coverage; never scans POI/edge objects."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.data.providers import OSMProvider, SyntheticProvider, demo_enabled, policy
from app.data.registry import acquisition, config_hash, freshness, permitted
from app.data.registry_schemas import (
    CoverageAssessment,
    CoverageQuery,
    CoverageResult,
    DataRequirement,
    DatasetCoverage,
    RegistryConfig,
    SufficiencyAssessment,
    SufficiencyDecision,
)
from app.data.schemas import ProviderDataset
from app.db.models import GeoDatasetRecord, ProviderDatasetRecord, WalkGraphRecord
from app.domain.enums import DataOrigin
from app.geo.provider import build_poi_query, build_query
from app.geo.walk_schemas import WalkGraphView


@dataclass(frozen=True)
class LocalDataset:
    metadata: ProviderDataset
    city: str
    categories: tuple[str, ...]
    imported_at: datetime | None = None


def read_metadata(session: Session, cap: int, demo: bool) -> tuple[list[LocalDataset], bool]:
    values: list[LocalDataset] = []
    complete = True
    geo = session.scalars(
        sa.select(GeoDatasetRecord)
        .where(GeoDatasetRecord.active)
        .order_by(GeoDatasetRecord.slug, GeoDatasetRecord.data_version)
        .limit(cap + 1)
    ).all()
    for row in geo[:cap]:
        try:
            meta = OSMProvider.metadata(row)
            attested = row.query in {build_query(meta.bbox), build_poi_query(meta.bbox)}
            complete &= attested
            values.append(
                LocalDataset(
                    meta,
                    row.city,
                    ("geo.mapped_poi", "geo.admin_polygons")
                    if row.query == build_query(meta.bbox)
                    else ("geo.mapped_poi",)
                    if attested
                    else (),
                    row.imported_at,
                )
            )
        except (ValidationError, ValueError, TypeError):
            complete = False
    graphs = session.scalars(
        sa.select(WalkGraphRecord)
        .where(WalkGraphRecord.active)
        .order_by(WalkGraphRecord.slug, WalkGraphRecord.graph_version)
        .limit(cap + 1)
    ).all()
    for graph in graphs[:cap]:
        try:
            view = WalkGraphView.model_validate(graph.document)
            m = view.manifest
            if view.graph_version != graph.graph_version or view.id != graph.id:
                raise ValueError
            meta = ProviderDataset(
                provider="osm",
                slug=graph.slug,
                revision=graph.graph_version,
                data_version=graph.graph_version,
                active=True,
                bbox=m.bbox,
                origin=DataOrigin.OPEN_DATA,
                source_name=m.source_name,
                source_url=None,
                license=m.license,
                attribution=m.attribution,
                observed_at=m.osm_base,
                generated_at=m.fetched_at,
                stale=(datetime.now(UTC) - m.osm_base).days > 30,
                stale_after_days=30,
                quality="mapping_completeness_unknown",
                limitations=("Walking topology only; not a vehicle routing network.",),
            )
            values.append(LocalDataset(meta, m.city, ("geo.pedestrian_network",), view.imported_at))
        except (ValidationError, ValueError, TypeError):
            complete = False
    scenario_rows = (
        session.scalars(
            sa.select(ProviderDatasetRecord)
            .where(ProviderDatasetRecord.active, ProviderDatasetRecord.provider == "synthetic")
            .order_by(ProviderDatasetRecord.slug, ProviderDatasetRecord.data_version)
            .limit(cap + 1)
        ).all()
        if demo
        else []
    )
    for scenario in scenario_rows[:cap]:
        try:
            values.append(
                LocalDataset(
                    SyntheticProvider.metadata(scenario),
                    "",
                    ("scenario.finance",),
                    scenario.imported_at,
                )
            )
        except (ValidationError, ValueError, HTTPException):
            complete = False
    complete &= max(len(geo), len(graphs), len(scenario_rows), len(values)) <= cap
    return values[:cap], complete


def spatial_fits(
    session: Session, query: CoverageQuery, datasets: list[LocalDataset]
) -> dict[int, str]:
    if query.aoi is None or not datasets:
        return {}
    # Only four scalar bounds per dataset cross the Python/SQL boundary. No large geometry.
    bounds = [{"n": n, **d.metadata.bbox.model_dump()} for n, d in enumerate(datasets)]
    rows = session.execute(
        sa.text("""
        WITH boxes AS (
          SELECT n, ST_MakeEnvelope(west,south,east,north,4326) AS g
          FROM jsonb_to_recordset(CAST(:boxes AS jsonb))
            AS b(n integer,west double precision,south double precision,
                 east double precision,north double precision)
        ), request AS (SELECT ST_MakeEnvelope(:west,:south,:east,:north,4326) AS g)
        SELECT n, CASE WHEN ST_Covers(b.g,r.g) THEN 'full_for_requested_scope'
          WHEN ST_Intersects(b.g,r.g) THEN 'partial' ELSE 'outside' END AS fit
        FROM boxes b CROSS JOIN request r
    """),
        {"boxes": json.dumps(bounds), **query.aoi.model_dump()},
    ).mappings()
    return {row["n"]: row["fit"] for row in rows}


def assess(
    query: CoverageQuery,
    registry: RegistryConfig,
    datasets: list[LocalDataset],
    complete: bool,
    fits: dict[int, str],
    now: datetime,
) -> CoverageResult:
    categories = {c.id: c for c in registry.categories}
    if not set(query.categories) <= categories.keys():
        raise HTTPException(422, detail={"code": "unknown_data_category"})
    policies = {p.id: p for p in registry.policies}
    territory = next((t for t in registry.territories if t.id == query.territory), None)
    answers = []
    for key in query.categories:
        category = categories[key]
        options = tuple(
            acquisition(s, query.purpose, key) for s in registry.sources if key in s.categories
        )
        evidence = []
        for n, data in enumerate(datasets):
            if category.private:
                continue
            meta = data.metadata
            source = next((s for s in registry.sources if s.id == meta.provider), None)
            if source is None or key not in data.categories or key not in source.categories:
                continue
            if meta.origin == DataOrigin.SYNTHETIC and query.mode != "demo":
                continue
            if query.aoi is not None:
                fit = fits.get(n, "unknown")
                if fit == "outside":
                    continue
                if meta.origin == DataOrigin.SYNTHETIC and query.aoi != meta.bbox:
                    fit = "partial"
            elif not category.spatial:
                fit = "full_for_requested_scope"
            elif territory:
                if data.city.casefold().strip() not in {
                    a.casefold().strip() for a in (territory.name, *territory.aliases)
                }:
                    continue
                fit = "partial"  # city identity is not a verified boundary
            else:
                fit = "unknown"
            if key == "geo.admin_polygons":
                fit = "partial"  # extract polygons do not attest a complete administrative layer
            fp = policies[source.freshness_policies[key]]
            source_time = meta.observed_at if meta.origin != DataOrigin.SYNTHETIC else None
            fresh = freshness(fp, now, source_time, meta.generated_at)
            temporal: Literal["snapshot_in_period", "outside_period", "unknown"] = "unknown"
            if query.period and source_time:
                if not query.period.start <= source_time <= query.period.end:
                    temporal = "outside_period"
                elif query.period.kind == "snapshot_window":
                    temporal = "snapshot_in_period"
            reasons = [
                "mapping_quality_unknown"
                if meta.origin == DataOrigin.OPEN_DATA
                else "scenario_not_observed"
            ]
            identity_matches = not query.territory or bool(
                territory
                and (
                    not data.city
                    or data.city.casefold().strip()
                    in {a.casefold().strip() for a in (territory.name, *territory.aliases)}
                )
            )
            if not identity_matches:
                reasons.append("territory_identity_unverified_for_extent")
            if fresh == "unknown":
                reasons.append("freshness_not_established")
            if not permitted(source, query.purpose):
                reasons.append("source_use_not_permitted")
            if temporal == "outside_period":
                reasons.append("requested_period_not_covered")
            if query.period and temporal == "unknown":
                reasons.append("temporal_coverage_unknown")
            evidence.append(
                DatasetCoverage.model_validate(
                    {
                        "metadata": meta.model_dump(
                            exclude={
                                "source_url",
                                "observed_at",
                                "generated_at",
                                "stale",
                                "stale_after_days",
                                "quality",
                            }
                        ),
                        "spatial_fit": fit,
                        "freshness": fresh,
                        "freshness_policy": fp.id,
                        "freshness_basis": fp.basis,
                        "temporal_fit": temporal,
                        "source_timestamp": source_time,
                        "generated_at": meta.generated_at
                        if meta.origin == DataOrigin.SYNTHETIC
                        else None,
                        "imported_at": data.imported_at,
                        "fetched_at": meta.generated_at
                        if meta.origin == DataOrigin.OPEN_DATA
                        else None,
                        "usable": identity_matches
                        and permitted(source, query.purpose)
                        and (not query.period or temporal == "snapshot_in_period"),
                        "reasons": reasons,
                    }
                )
            )
        usable = [e for e in evidence if e.usable]
        current = [e for e in usable if e.freshness == "current"]
        full = [e for e in usable if e.spatial_fit == "full_for_requested_scope"]
        status = "unknown"
        if any(e in current for e in full):
            status = "available"
        elif full and all(e.freshness == "stale" for e in full):
            status = "stale"
        elif any(e.spatial_fit == "partial" for e in usable):
            status = "partial"
        elif not evidence and complete and (not category.spatial or territory or query.aoi):
            status = "missing"
        if category.private or (query.territory and territory is None and query.aoi is None):
            status = "unknown"
        summary = "unknown"
        if status == "available":
            summary = "usable"
        elif status in {"partial", "stale"}:
            summary = status
        elif status == "missing":
            if any(o.acquirability == "permitted" for o in options):
                summary = "acquirable"
            elif any(o.acquirability == "unavailable" for o in options):
                summary = "source_unavailable"
            elif not options or all(o.acquirability == "forbidden" for o in options):
                summary = "not_available_from_approved_sources"
        reasons = []
        if not complete:
            reasons.append("metadata_incomplete_or_limit")
        if category.private:
            reasons.append("private_inputs_not_in_public_catalog")
        if category.spatial and query.territory:
            reasons.append("territory_boundary_unknown")
        answers.append(
            CoverageAssessment.model_validate(
                {
                    "category": key,
                    "local_status": status,
                    "summary": summary,
                    "availability": "present"
                    if evidence
                    else "missing"
                    if status == "missing"
                    else "unknown",
                    "freshness": "current"
                    if current
                    else "stale"
                    if usable and all(e.freshness == "stale" for e in usable)
                    else "unknown",
                    "completeness": "full_for_requested_scope"
                    if full
                    else "partial"
                    if evidence
                    else "unknown",
                    "datasets": evidence,
                    "acquisition": options,
                    "reasons": reasons,
                    "object_quality": "not_applicable"
                    if evidence and all(e.metadata.origin == DataOrigin.SYNTHETIC for e in evidence)
                    else "unknown",
                }
            )
        )
    return CoverageResult(
        registry_revision=registry.revision,
        config_sha256=config_hash(registry),
        evaluated_at=now,
        query=query,
        assessments=tuple(answers),
        metadata_complete=complete,
        limitations=(
            "Coverage describes imported snapshots, not completeness of the real market.",
            "Source timestamp is not a real-world observation date. "
            "No external requests performed.",
        ),
    )


def coverage(session: Session, query: CoverageQuery, registry: RegistryConfig) -> CoverageResult:
    policy(query.mode)
    if not set(query.categories) <= {c.id for c in registry.categories}:
        raise HTTPException(422, detail={"code": "unknown_data_category"})
    datasets, complete = read_metadata(
        session, registry.max_datasets, query.mode == "demo" and demo_enabled()
    )
    return assess(
        query,
        registry,
        datasets,
        complete,
        spatial_fits(session, query, datasets),
        datetime.now(UTC),
    )


def sufficiency(
    requirements: tuple[DataRequirement, ...], result: CoverageResult
) -> tuple[SufficiencyDecision, ...]:
    if len(requirements) > 20 or len({r.id for r in requirements}) != len(requirements):
        raise ValueError("Invalid bounded requirements")
    decisions = []
    for r in requirements:
        found = next((a for a in result.assessments if a.category == r.category), None)
        state = "unknown" if found is None else found.local_status
        allowed = (
            bool(
                found
                and any(
                    e.usable
                    and e.metadata.origin in r.accepted_origins
                    and e.metadata.origin != DataOrigin.SYNTHETIC
                    and e.freshness == "current"
                    and (
                        e.spatial_fit == "full_for_requested_scope"
                        or r.allow_partial
                        and e.spatial_fit == "partial"
                    )
                    for e in found.datasets
                )
            )
            and not r.require_known_quality
        )
        action = "use_pinned" if allowed else "block"
        if not allowed:
            if not r.required:
                action = "omit_optional"
            elif found and any(a.acquirability == "permitted" for a in found.acquisition):
                action = "request_acquisition"
            elif state == "stale":
                action = "cache_revalidate"
            elif r.category.startswith(("user.", "scenario.")):
                action = "ask_user"
        decisions.append(
            SufficiencyDecision.model_validate(
                {
                    "requirement_id": r.id,
                    "state": "sufficient"
                    if allowed
                    else state
                    if state != "available"
                    else "unknown",
                    "action": action,
                    "technically_eligible": allowed,
                    "quality": found.object_quality if found else "unknown",
                    "reasons": ("technical_eligibility_is_not_business_validity",)
                    if allowed
                    else ("requirements_not_satisfied",),
                }
            )
        )
    return tuple(decisions)


def assess_sufficiency(
    requirements: tuple[DataRequirement, ...],
    result: CoverageResult,
    revision: str,
) -> SufficiencyAssessment:
    decisions = sufficiency(requirements, result)
    allowed: list[str] = []
    blocked: list[str] = []
    for task in sorted({task for r in requirements for task in r.critical_for}):
        required = [
            d
            for r, d in zip(requirements, decisions, strict=True)
            if r.required and task in r.critical_for
        ]
        (allowed if required and all(d.technically_eligible for d in required) else blocked).append(
            task
        )
    return SufficiencyAssessment(
        requirements_revision=revision,
        evaluated_at=result.evaluated_at,
        decisions=decisions,
        allowed_tasks=tuple(allowed),
        blocked_tasks=tuple(blocked),
    )

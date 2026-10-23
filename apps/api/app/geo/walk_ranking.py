from datetime import UTC, datetime
from typing import Any

from pydantic import Field
from sqlalchemy.orm import Session

from app.api.schemas import Contract
from app.bank.matching import digest
from app.geo.ranking import rank_candidates
from app.geo.ranking_schemas import (
    RankingCollection,
    RankingRequest,
    RawGeoMetrics,
    ScoreExplanation,
    ZoneEvaluation,
)
from app.geo.scoring import score_components
from app.geo.walk_schemas import CatchmentRequest, CatchmentResult
from app.geo.walking import LIMITATIONS, catchment, graph_for

VERSION = "osm-foot-cohort-minmax-v1"


class WalkingRankingRequest(Contract):
    ranking: RankingRequest
    max_snap_m: int = Field(default=30, strict=True, ge=0, le=100)
    graph_version: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class WalkingRankingResult(Contract):
    baseline: RankingCollection
    network: RankingCollection
    catchments: dict[str, CatchmentResult]
    methodology: str = (
        "Separate opt-in comparison; BA-008 remains straight-line. "
        "Identical weights/min-max, different explicitly versioned network inputs."
    )


def rank_walking(session: Session, slug: str, body: WalkingRankingRequest) -> WalkingRankingResult:
    baseline = rank_candidates(session, slug, body.ranking)
    graph = graph_for(session, slug, body.graph_version)
    policy = baseline.policy.model_copy(
        update={
            "version": "osm-business-context-walking-v1",
            "fingerprint": digest(
                {
                    "base": baseline.policy.fingerprint,
                    "graph": graph.graph_version if graph else None,
                    "snap": body.max_snap_m,
                    "algorithm": VERSION,
                }
            ),
        }
    )
    data: dict[str, CatchmentResult] = {}
    metrics: dict[str, RawGeoMetrics] = {}
    for candidate in baseline.candidates.features:
        lon, lat = candidate.properties.representative_point.coordinates
        c = catchment(
            session,
            slug,
            CatchmentRequest(
                longitude=lon,
                latitude=lat,
                distance_m=body.ranking.scoring.radius_m,
                max_snap_m=body.max_snap_m,
                data_version=baseline.candidates.dataset.data_version,
                graph_version=graph.graph_version if graph else None,
            ),
        )
        data[candidate.id] = c

        def count(categories: tuple[str, ...]) -> int:
            return sum(
                bool(set(p.properties["categories"]) & set(categories)) for p in c.pois.features
            )

        def nearest(categories: tuple[str, ...]) -> float | None:
            values = [
                float(p.properties["network_distance_m"])
                for p in c.pois.features
                if set(p.properties["categories"]) & set(categories)
            ]
            return min(values) if values else None

        metrics[candidate.id] = RawGeoMetrics(
            distance_method="walking_network_with_connectors",
            coverage_margin_m=c.coverage_margin_m or 0,
            fully_covered=c.fully_covered and c.status == "ok",
            mapped_poi_count=c.reachable_poi_count,
            transit_count=count(policy.transit),
            nearest_transit_m=nearest(policy.transit),
            competitor_count=count(policy.competitors),
            nearest_competitor_m=nearest(policy.competitors),
            competitor_features_per_km2=None,
            infrastructure_count=count(policy.infrastructure),
            infrastructure_categories=tuple(
                k for k in policy.infrastructure if c.category_counts.get(k, 0) > 0
            ),
            complementary_count=count(policy.complementary),
            category_counts=c.category_counts,
        )
    components, comparable = score_components(metrics, body.ranking.scoring)
    evaluations = []
    originals = {e.candidate_id: e for e in baseline.evaluations}
    for key, raw in metrics.items():
        original = originals.get(key)
        if original is None:
            continue
        explanations = tuple(
            ScoreExplanation(
                criterion=c.criterion,
                effect="unavailable" if c.status not in {"available", "disabled"} else "neutral",
                text=f"Критерий {c.criterion}: raw={c.raw_value}, norm={c.normalized}, "
                f"вклад={c.contribution}. Те же веса/min-max, но POI отобраны по дорожному "
                "бюджету с явными соединителями. Разница отражает обход по графу и "
                "неполноту привязки, а не изменение спроса.",
            )
            for c in components[key]
        )
        evaluations.append(
            ZoneEvaluation(
                candidate_id=key,
                algorithm_version=VERSION,
                policy_fingerprint=policy.fingerprint,
                status="ranked" if key in comparable else "insufficient_data",
                score=round(sum(c.contribution or 0 for c in components[key]), 6)
                if key in comparable
                else None,
                raw=raw,
                provenance=original.provenance.model_copy(
                    update={"generated_at": datetime.now(UTC), "limitations": LIMITATIONS}
                ),
                components=components[key],
                explanations=explanations,
                missing_data=tuple(
                    m for m in original.missing_data if m != "walking_network_and_barriers"
                )
                + ("unverified_snap_connectors_and_incomplete_osm_network",)
                + data[key].reasons,
            )
        )
    evaluations.sort(key=lambda e: (e.score is None, -(e.score or 0), e.candidate_id))
    evaluations = [
        e.model_copy(update={"rank": i + 1}) if e.score is not None else e
        for i, e in enumerate(evaluations)
    ]
    updates: dict[str, Any] = {
        "evaluations": tuple(evaluations),
        "algorithm_version": VERSION,
        "policy": policy,
        "comparison_ids": comparable,
        "limitations": LIMITATIONS,
        "request_fingerprint": digest(
            {
                "baseline": baseline.request_fingerprint,
                "policy": policy.fingerprint,
                "catchments": {k: c.request_fingerprint for k, c in data.items()},
            }
        ),
        "reasons": ("explicit_opt_in_network_comparison_not_profitability",),
        "missing_data": tuple(
            m for m in baseline.missing_data if m != "walking_network_and_barriers"
        )
        + ("network_completeness_and_entrances",),
    }
    if evaluations:
        updates["status"] = (
            "ok"
            if len(comparable) == len(evaluations)
            else ("partial" if comparable else "insufficient_data")
        )
    network = baseline.model_copy(update=updates)
    return WalkingRankingResult(baseline=baseline, network=network, catchments=data)

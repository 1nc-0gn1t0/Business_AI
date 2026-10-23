import hashlib
import math
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.enums import ConfirmationState
from app.geo.candidates import generate
from app.geo.ranking_schemas import (
    ObservationProvenance,
    RankingCollection,
    RankingRequest,
    RawGeoMetrics,
    ScoreComponent,
    ScoreExplanation,
    ZoneEvaluation,
)
from app.geo.scoring import (
    ALGORITHM_VERSION,
    LIMITATIONS,
    MISSING_DATA,
    resolve_policy,
    score_components,
)
from app.geo.service import GeoData

METRICS_SQL = """
WITH point AS (SELECT ST_SetSRID(ST_MakePoint(:lon,:lat),4326) g),
nearby AS MATERIALIZED (
 SELECT p.categories,ST_Distance(p.geom::geography,c.g::geography) distance
 FROM geo_pois p CROSS JOIN point c WHERE p.dataset_id=:dataset_id
 AND ST_DWithin(p.geom::geography,c.g::geography,:radius)
), categories AS (
 SELECT category,count(*) n FROM nearby n CROSS JOIN LATERAL unnest(n.categories) category
 GROUP BY category
)
SELECT ST_Distance(c.g::geography,ST_Segmentize(ST_Boundary(
 ST_MakeEnvelope(:west,:south,:east,:north,4326)),0.001)::geography) coverage_margin_m,
 (SELECT count(*) FROM nearby) mapped_poi_count,
 (SELECT count(*) FROM nearby WHERE categories && CAST(:transit AS text[])) transit_count,
 (SELECT min(distance) FROM nearby WHERE categories && CAST(:transit AS text[])) nearest_transit_m,
 (SELECT count(*) FROM nearby WHERE categories && CAST(:competitors AS text[])) competitor_count,
 (SELECT min(distance) FROM nearby WHERE categories && CAST(:competitors AS text[]))
 nearest_competitor_m,
 (SELECT count(*) FROM nearby WHERE categories && CAST(:infrastructure AS text[]))
 infrastructure_count,
 ARRAY(SELECT category FROM categories WHERE category=ANY(CAST(:infrastructure AS text[]))
 ORDER BY category) infrastructure_categories,
 (SELECT count(*) FROM nearby WHERE categories && CAST(:complementary AS text[]))
 complementary_count,
 (SELECT coalesce(jsonb_object_agg(category,n),'{}'::jsonb) FROM categories) category_counts
FROM point c
"""


def explanations(
    raw: RawGeoMetrics, components: tuple[ScoreComponent, ...]
) -> tuple[ScoreExplanation, ...]:
    details = {
        "transit": f"Выгрузка содержит {raw.transit_count} остановок в радиусе наблюдения. "
        + (
            f"Ближайшая — {raw.nearest_transit_m:.1f} м по прямой. "
            if raw.nearest_transit_m is not None
            else "Расстояние до остановки неизвестно. "
        ),
        "infrastructure": f"Найдено {len(raw.infrastructure_categories)} категорий инфраструктуры "
        f"({raw.infrastructure_count} OSM-объектов). ",
        "complementary": f"Найдено {raw.complementary_count} OSM-объектов "
        "из списка отраслевого окружения. Это не измеренная аудитория или спрос. ",
        "competitors": f"Найдено {raw.competitor_count} потенциально конкурирующих OSM-объектов; "
        f"{raw.competitor_features_per_km2 or 0:.1f} объектов/км² круга наблюдения. "
        "Количество не доказывает насыщение или спрос. ",
    }
    result = []
    for c in components:
        effect = "neutral"
        text = details[c.criterion]
        if c.status == "disabled":
            text += "Вес равен нулю; в итоговый балл не входит."
        elif c.status != "available":
            effect = "unavailable"
            text += "Сравнительная оценка недоступна: неполное покрытие или недостаточно данных."
        elif c.normalized is not None:
            effect = (
                "strength"
                if c.normalized >= 0.67
                else ("weakness" if c.normalized <= 0.33 else "neutral")
            )
            text += f"Относительный показатель {c.normalized:.3f}; вклад {c.contribution:.3f} "
            text += "балла из 100 по явной настройке, только среди сравниваемых зон."
        result.append(
            ScoreExplanation.model_validate(
                {"criterion": c.criterion, "effect": effect, "text": text}
            )
        )
    return tuple(result)


def rank_candidates(session: Session, slug: str, request: RankingRequest) -> RankingCollection:
    candidates = generate(session, slug, request.candidates)
    policy = resolve_policy(candidates.profile_snapshot.category or "", request.scoring)
    digest = hashlib.sha256(
        ":".join(
            (
                ALGORITHM_VERSION,
                candidates.request_fingerprint,
                policy.fingerprint,
                candidates.spatial_runtime,
            )
        ).encode()
    ).hexdigest()
    base: dict[str, Any] = {
        "candidates": candidates,
        "algorithm_version": ALGORITHM_VERSION,
        "policy": policy,
        "request_fingerprint": digest,
        "missing_data": MISSING_DATA,
        "limitations": LIMITATIONS,
    }
    if candidates.profile_snapshot.confirmation_state != ConfirmationState.CONFIRMED:
        return RankingCollection.model_validate(
            base
            | {
                "status": "needs_confirmation",
                "reasons": ["confirmed_profile_snapshot_required"],
            }
        )
    if not candidates.features:
        return RankingCollection.model_validate(
            base
            | {
                "status": "no_candidates"
                if candidates.status == "no_candidates"
                else "insufficient_data",
                "reasons": candidates.reasons,
            }
        )
    record = GeoData(session).dataset(slug, candidates.dataset.data_version)
    now = datetime.now(UTC)
    provenance = ObservationProvenance(
        source_name=candidates.dataset.source_name,
        source_url=record.source_url,
        data_version=record.data_version,
        observed_at=record.osm_base,
        generated_at=now,
        limitations=LIMITATIONS + tuple(candidates.dataset.limitations),
    )
    metrics: dict[str, RawGeoMetrics] = {}
    for candidate in candidates.features:
        lon, lat = candidate.properties.representative_point.coordinates
        params = record.bbox | {
            "dataset_id": record.id,
            "lon": lon,
            "lat": lat,
            "radius": request.scoring.radius_m,
            "transit": list(policy.transit),
            "competitors": list(policy.competitors),
            "infrastructure": list(policy.infrastructure),
            "complementary": list(policy.complementary),
        }
        row = dict(session.execute(sa.text(METRICS_SQL), params).mappings().one())
        row["fully_covered"] = row["coverage_margin_m"] >= request.scoring.radius_m + 1
        row["competitor_features_per_km2"] = row["competitor_count"] / (
            math.pi * (request.scoring.radius_m / 1000) ** 2
        )
        metrics[candidate.id] = RawGeoMetrics.model_validate(row)
    components, comparable = score_components(metrics, request.scoring)
    evaluations = []
    for key, raw in metrics.items():
        missing = list(MISSING_DATA)
        if not raw.fully_covered:
            missing.append("observation_circle_outside_coverage_counts_are_lower_bounds")
        if not comparable:
            missing.append("insufficient_comparable_zones_or_missing_weighted_signal")
        missing.extend(
            f"weighted_signal_unavailable:{c.criterion}"
            for c in components[key]
            if c.status == "unavailable" and c.weight > 0
        )
        scored = key in comparable
        evaluations.append(
            ZoneEvaluation(
                candidate_id=key,
                algorithm_version=ALGORITHM_VERSION,
                policy_fingerprint=policy.fingerprint,
                status="ranked"
                if scored
                else ("outside_coverage" if not raw.fully_covered else "insufficient_data"),
                score=round(sum(c.contribution or 0 for c in components[key]), 6)
                if scored
                else None,
                raw=raw,
                provenance=provenance,
                components=components[key],
                explanations=explanations(raw, components[key]),
                missing_data=tuple(missing),
            )
        )
    evaluations.sort(key=lambda e: (e.score is None, -(e.score or 0), e.candidate_id))
    evaluations = [
        e.model_copy(update={"rank": index + 1}) if e.score is not None else e
        for index, e in enumerate(evaluations)
    ]
    reasons = ["relative_geographic_proxies_not_profitability", "straight_line_not_walking"]
    if len(comparable) != len(metrics):
        reasons.append("incomplete_or_insufficient_comparison")
    if candidates.dataset.stale:
        reasons.append("stale_osm_snapshot")
    status = (
        "insufficient_data"
        if not comparable
        else (
            "partial" if len(comparable) != len(metrics) or candidates.status == "partial" else "ok"
        )
    )
    return RankingCollection.model_validate(
        base
        | {
            "status": status,
            "reasons": reasons,
            "evaluations": evaluations,
            "comparison_ids": comparable,
        }
    )

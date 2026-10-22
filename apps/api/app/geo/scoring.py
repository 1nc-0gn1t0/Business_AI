import hashlib
import json

from app.geo.candidate_policy import business_key
from app.geo.ranking_schemas import (
    Criterion,
    RawGeoMetrics,
    ResolvedScoringPolicy,
    ScoreComponent,
    ScoringConfig,
)

ALGORITHM_VERSION = "osm-cohort-minmax-v1"
CRITERIA: tuple[Criterion, ...] = ("transit", "infrastructure", "complementary", "competitors")
INFRASTRUCTURE = (
    "amenity:bank",
    "amenity:atm",
    "amenity:post_office",
    "amenity:pharmacy",
    "amenity:clinic",
    "amenity:hospital",
    "amenity:parking",
    "amenity:bicycle_parking",
)
BUSINESS_CONTEXT = {
    "coffee": (
        ("amenity:cafe",),
        (
            "amenity:university",
            "amenity:college",
            "amenity:school",
            "shop:bakery",
            "shop:supermarket",
            "shop:convenience",
        ),
    ),
    "bakery": (
        ("shop:bakery",),
        ("amenity:cafe", "amenity:school", "shop:supermarket", "shop:convenience"),
    ),
    "restaurant": (
        ("amenity:restaurant", "amenity:fast_food"),
        ("amenity:university", "amenity:college", "amenity:cinema", "shop:mall"),
    ),
    "salon": (
        ("shop:hairdresser", "shop:beauty"),
        ("shop:clothes", "shop:supermarket", "shop:convenience", "amenity:cafe"),
    ),
    "grocery": (
        ("shop:supermarket", "shop:convenience"),
        ("amenity:school", "amenity:kindergarten", "amenity:university"),
    ),
}
MISSING_DATA = (
    "premises_availability",
    "rent_and_budget_feasibility",
    "floor_area_and_land_use",
    "walking_network_and_barriers",
    "measured_traffic",
    "measured_demand",
    "purchasing_power",
    "revenue_and_profitability",
)
LIMITATIONS = (
    "Comparative mapped geographic context only; not a forecast of business profitability.",
    "OSM tagging completeness is unknown even inside the extract; zero is not proof of absence.",
    "Counts describe OSM features, not deduplicated businesses or people; "
    "centers are not entrances.",
    "All distances are geodesic straight lines from the zone representative point, "
    "not walking routes.",
    "Weights and category relevance are explicit expert hypotheses, "
    "not trained demand coefficients.",
    "Budget, funding and format have no numerical effect without premises/cost data.",
    "Scores depend on the compared candidates and cannot be compared across requests or radii.",
)


def resolve_policy(category: str, config: ScoringConfig) -> ResolvedScoringPolicy:
    business = business_key(category)
    competitors, complementary = BUSINESS_CONTEXT.get(business, ((), ()))
    values = {
        "version": "osm-business-context-v1",
        "business": business,
        "config": config,
        "competitors": competitors,
        "complementary": complementary,
        "infrastructure": INFRASTRUCTURE,
        "weight_rationale": "Default weights give equal influence to three distinct observable "
        "dimensions (transport proximity, service diversity, complementary POI). No empirical "
        "evidence justifies preferring one. Competition is neutral by default. Overrides are "
        "explicit caller hypotheses; their exact values and modes are hashed, "
        "not validated by data.",
    }
    serial = {**values, "config": config.model_dump(mode="json")}
    digest = hashlib.sha256(json.dumps(serial, sort_keys=True).encode()).hexdigest()
    return ResolvedScoringPolicy.model_validate(values | {"fingerprint": digest})


def normalize_values(values: list[float], reverse: bool = False) -> list[float | None]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high == 0:
        return [None] * len(values)
    if high == low:
        return [0.5] * len(values)
    result = [(value - low) / (high - low) for value in values]
    return [(1 - value if reverse else value) for value in result]


def feature_values(raw: RawGeoMetrics, config: ScoringConfig) -> dict[Criterion, float]:
    return {
        "transit": 0
        if raw.nearest_transit_m is None
        else max(0, 1 - raw.nearest_transit_m / config.radius_m),
        "infrastructure": float(len(raw.infrastructure_categories)),
        "complementary": float(raw.complementary_count),
        "competitors": float(raw.competitor_count),
    }


def score_components(
    metrics: dict[str, RawGeoMetrics],
    config: ScoringConfig,
) -> tuple[dict[str, tuple[ScoreComponent, ...]], tuple[str, ...]]:
    covered = sorted(key for key, raw in metrics.items() if raw.fully_covered)
    weights = config.weights.model_dump()
    total = sum(weights.values())
    normalized: dict[Criterion, dict[str, float | None]] = {}
    ranges: dict[Criterion, tuple[float | None, float | None]] = {}
    for criterion in CRITERIA:
        values = [feature_values(metrics[key], config)[criterion] for key in covered]
        normal = normalize_values(
            values, reverse=(criterion == "competitors" and config.competitor_mode == "separation")
        )
        normalized[criterion] = dict(zip(covered, normal, strict=True))
        ranges[criterion] = (min(values), max(values)) if values else (None, None)
    comparable = (
        tuple(covered)
        if len(covered) >= 2
        and all(
            all(normalized[c].get(key) is not None for c in CRITERIA if weights[c] > 0)
            for key in covered
        )
        else ()
    )
    result: dict[str, tuple[ScoreComponent, ...]] = {}
    for key, raw in metrics.items():
        components = []
        for c in CRITERIA:
            value = normalized[c].get(key) if len(covered) >= 2 else None
            weight = weights[c] / total
            status = "available" if value is not None else "unavailable"
            if weight == 0:
                status = "disabled"
            elif not raw.fully_covered:
                status = "outside_coverage"
            components.append(
                ScoreComponent.model_validate(
                    {
                        "criterion": c,
                        "raw_value": feature_values(raw, config)[c],
                        "unit": "proximity_fraction"
                        if c == "transit"
                        else (
                            "mapped_category_count"
                            if c == "infrastructure"
                            else "mapped_feature_count"
                        ),
                        "normalized": value if weight else None,
                        "normalization_min": ranges[c][0],
                        "normalization_max": ranges[c][1],
                        "weight": weight,
                        "contribution": 100 * weight * value
                        if value is not None and weight
                        else (0.0 if not weight else None),
                        "status": status,
                    }
                )
            )
        result[key] = tuple(components)
    return result, comparable

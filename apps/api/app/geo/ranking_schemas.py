from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.api.schemas import Contract
from app.geo.candidate_schemas import CandidateCollection, CandidateRequest, Category

Criterion = Literal["transit", "infrastructure", "complementary", "competitors"]
Weight = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class ScoringWeights(Contract):
    transit: Weight = 1.0
    infrastructure: Weight = 1.0
    complementary: Weight = 1.0
    competitors: Weight = 0.0


class ScoringConfig(Contract):
    version: Literal["osm-relative-v1"] = "osm-relative-v1"
    radius_m: int = Field(default=500, ge=50, le=2000)
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    competitor_mode: Literal["neutral", "cluster", "separation"] = "neutral"

    @model_validator(mode="after")
    def valid_weights(self) -> Self:
        if sum(self.weights.model_dump().values()) <= 0:
            raise ValueError("At least one positive weight is required")
        if (self.competitor_mode == "neutral") != (self.weights.competitors == 0):
            raise ValueError("Neutral competition requires weight=0; other modes require weight>0")
        return self


class RankingRequest(Contract):
    candidates: CandidateRequest
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)


class ResolvedScoringPolicy(Contract):
    version: str
    fingerprint: str
    business: str
    config: ScoringConfig
    competitors: tuple[Category, ...]
    infrastructure: tuple[Category, ...]
    complementary: tuple[Category, ...]
    transit: tuple[Category, ...] = ("highway:bus_stop",)
    weight_rationale: str


class RawGeoMetrics(Contract):
    distance_method: Literal["geodesic_straight_line", "walking_network_with_connectors"] = (
        "geodesic_straight_line"
    )
    coverage_margin_m: float
    fully_covered: bool
    mapped_poi_count: int
    transit_count: int
    nearest_transit_m: float | None
    competitor_count: int
    nearest_competitor_m: float | None
    competitor_features_per_km2: float | None
    infrastructure_count: int
    infrastructure_categories: tuple[str, ...]
    complementary_count: int
    category_counts: dict[str, int]


class ObservationProvenance(Contract):
    origin: Literal["open_data"] = "open_data"
    source_name: str
    source_url: str
    data_version: str
    observed_at: AwareDatetime
    generated_at: AwareDatetime
    license: Literal["ODbL-1.0"] = "ODbL-1.0"
    confidence: Literal["low"] = "low"
    limitations: tuple[str, ...]


class ScoreComponent(Contract):
    criterion: Criterion
    raw_value: float | None
    unit: str
    normalized: float | None
    normalization_min: float | None
    normalization_max: float | None
    weight: float
    contribution: float | None
    status: Literal["available", "disabled", "unavailable", "outside_coverage"]


class ScoreExplanation(Contract):
    criterion: Criterion
    effect: Literal["strength", "weakness", "neutral", "unavailable"]
    text: str


class ZoneEvaluation(Contract):
    candidate_id: str
    algorithm_version: str
    policy_fingerprint: str
    origin: Literal["modelled"] = "modelled"
    rank: int | None = None
    score: float | None = None
    status: Literal["ranked", "outside_coverage", "insufficient_data"]
    raw: RawGeoMetrics
    provenance: ObservationProvenance
    components: tuple[ScoreComponent, ...]
    explanations: tuple[ScoreExplanation, ...]
    missing_data: tuple[str, ...]


class RankingCollection(Contract):
    status: Literal["ok", "partial", "no_candidates", "needs_confirmation", "insufficient_data"]
    reasons: tuple[str, ...]
    candidates: CandidateCollection
    evaluations: tuple[ZoneEvaluation, ...] = ()
    algorithm_version: str
    score_semantics: Literal["comparative_mapped_geographic_context"] = (
        "comparative_mapped_geographic_context"
    )
    tie_breaker: Literal["score_desc_then_candidate_id_asc"] = "score_desc_then_candidate_id_asc"
    policy: ResolvedScoringPolicy
    request_fingerprint: str
    comparison_ids: tuple[str, ...] = ()
    missing_data: tuple[str, ...]
    limitations: tuple[str, ...]

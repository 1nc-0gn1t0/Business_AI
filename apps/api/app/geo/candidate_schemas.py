from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.api.schemas import BusinessProfile, Contract
from app.geo.schemas import Bounds, DatasetView, MultiPolygonGeometry, POIFeature, PointGeometry

Category = Annotated[str, StringConstraints(pattern=r"^(amenity|shop|highway):[a-z0-9_]+$")]
Version = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ProximityRequirement(Contract):
    category: Category
    max_distance_m: float = Field(gt=0, le=2000, allow_inf_nan=False)
    min_count: int = Field(default=1, ge=1, le=10)
    profile_constraint: str | None = Field(default=None, min_length=1, max_length=300)


class CandidateRequest(Contract):
    profile: BusinessProfile
    data_version: Version | None = None
    search_bbox: Bounds | None = None
    district_ids: tuple[int, ...] = Field(default=(), max_length=20)
    excluded_district_ids: tuple[int, ...] = Field(default=(), max_length=20)
    cell_size_m: int = Field(default=500, ge=250, le=2000)
    min_separation_m: int = Field(default=500, ge=0, le=10000)
    limit: int = Field(default=5, ge=1, le=10)
    requirements: tuple[ProximityRequirement, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def valid_constraints(self) -> Self:
        for ids in (self.district_ids, self.excluded_district_ids):
            if len(set(ids)) != len(ids) or any(value <= 0 for value in ids):
                raise ValueError("District IDs must be positive and unique")
        bindings = [r.profile_constraint for r in self.requirements if r.profile_constraint]
        if len(bindings) != len(set(bindings)) or not set(bindings).issubset(
            self.profile.preferences.constraints
        ):
            raise ValueError("Each binding must name a unique existing profile constraint")
        return self


class RequirementEvidence(Contract):
    requirement: ProximityRequirement
    mapped_count: int


class CandidateProperties(Contract):
    origin: Literal["modelled"] = "modelled"
    kind: Literal["geographic_zone_not_premises"] = "geographic_zone_not_premises"
    is_actual_listing: Literal[False] = False
    grid_i: int
    grid_j: int
    area_m2: float
    representative_point: PointGeometry
    anchor: POIFeature
    requirements: tuple[RequirementEvidence, ...]


class CandidateFeature(Contract):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: MultiPolygonGeometry
    properties: CandidateProperties


class CandidateCollection(Contract):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: tuple[CandidateFeature, ...] = ()
    status: Literal["ok", "partial", "no_candidates", "insufficient_data", "needs_constraints"]
    reasons: tuple[str, ...]
    dataset: DatasetView
    profile_snapshot: BusinessProfile
    request_snapshot: CandidateRequest
    algorithm_version: str
    policy_version: str
    request_fingerprint: str
    metric_srid: int
    geometry_srid: Literal[4326] = 4326
    spatial_runtime: str
    eligible_count: int = 0
    requested_count: int
    coverage: Literal["saved_bbox_only"] = "saved_bbox_only"
    not_evaluated: tuple[str, ...]

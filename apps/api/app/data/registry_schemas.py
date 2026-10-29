"""Versioned public metadata; v1 provider/metric contracts remain unchanged."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from app.api.schemas import Contract
from app.data.schemas import DataMode, ProviderId, Version
from app.domain.enums import DataOrigin
from app.geo.schemas import Bounds, Slug

Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
LocalState = Literal["available", "partial", "stale", "missing", "unknown"]
Freshness = Literal["current", "stale", "unknown"]
Acquirability = Literal["permitted", "forbidden", "unavailable", "not_integrated", "unknown"]


class DataCategory(Contract):
    id: Key
    name: Text
    spatial: bool
    private: bool = False
    unit: Text


class FreshnessPolicy(Contract):
    id: Key
    basis: Literal["source_timestamp", "period_end", "generated_at", "unknown"]
    max_age_days: int | None = Field(default=None, strict=True, ge=1, le=36500)
    rationale: Text


class SourceDefinition(Contract):
    id: Key
    adapter_id: Key
    revision: Key
    name: Text
    legacy_name: Text
    source_type: Literal["open", "licensed", "official", "user", "scenario", "placeholder"]
    origin: DataOrigin
    adapter_status: Literal["ready", "not_integrated"]
    categories: tuple[Key, ...] = Field(min_length=1, max_length=30)
    acquisition_methods: tuple[Literal["local_read", "offline_import", "operator_fetch"], ...]
    geographic_scope: Literal["global_source", "authored_extent", "unknown"]
    license_id: Text | None
    license_status: Literal["verified_local_use", "review_required", "forbidden"]
    attribution: Text
    allowed_uses: tuple[Literal["local_analysis", "redistribution"], ...]
    network_permission: Literal["permitted", "review_required", "forbidden"]
    availability: Literal["ready", "degraded", "unavailable", "not_integrated", "unknown"]
    freshness_policies: dict[Key, Key] = Field(max_length=30)
    policy_revision: Key
    policy_note: Text
    resource_policy_ref: Key
    license_reviewed_at: AwareDatetime | None = None
    availability_checked_at: AwareDatetime | None = None
    acquisition_scope: Literal["disabled", "operator_smoke"] = "disabled"
    acquisition_approved_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def license_required(self) -> Self:
        if self.license_status == "verified_local_use" and self.license_id is None:
            raise ValueError("Verified use requires a license identifier")
        return self


class Territory(Contract):
    id: Key
    name: Text
    aliases: tuple[Text, ...] = Field(max_length=10)
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")] = "RU"
    region: Text | None = None
    # These are identities, not claims of an imported administrative boundary.
    boundary_status: Literal["unknown"] = "unknown"


class RegistryConfig(Contract):
    schema_version: Literal["data-registry-v2"] = "data-registry-v2"
    revision: Key
    sources: tuple[SourceDefinition, ...] = Field(min_length=1, max_length=32)
    categories: tuple[DataCategory, ...] = Field(min_length=1, max_length=64)
    policies: tuple[FreshnessPolicy, ...] = Field(min_length=1, max_length=64)
    territories: tuple[Territory, ...] = Field(max_length=100)
    max_datasets: int = Field(default=100, strict=True, ge=1, le=1000)

    @model_validator(mode="after")
    def references(self) -> Self:
        for values in (self.sources, self.categories, self.policies, self.territories):
            if len({value.id for value in values}) != len(values):
                raise ValueError("Duplicate registry identifier")
        categories = {c.id for c in self.categories}
        policies = {p.id for p in self.policies}
        for source in self.sources:
            if (
                not set(source.categories) <= categories
                or set(source.freshness_policies) != set(source.categories)
                or not set(source.freshness_policies.values()) <= policies
            ):
                raise ValueError("Invalid source category/freshness reference")
            if source.adapter_status == "ready" and source.adapter_id not in {"osm", "synthetic"}:
                raise ValueError("Unimplemented adapter cannot be ready")
        if not {"osm", "synthetic", "ghsl", "licensed"} <= {s.id for s in self.sources}:
            raise ValueError("Legacy provider registrations are required")
        origins = {
            "osm": "open_data",
            "synthetic": "synthetic",
            "ghsl": "modelled",
            "licensed": "licensed",
        }
        for source in self.sources:
            if source.id in origins and (
                source.adapter_id != source.id or source.origin != origins[source.id]
            ):
                raise ValueError("Legacy provider identity/origin cannot be relabelled")
            if (source.source_type == "scenario") != (source.origin == DataOrigin.SYNTHETIC):
                raise ValueError("Scenarios cannot be registered as observations")
            if source.origin != DataOrigin.SYNTHETIC and any(
                p.basis == "generated_at" and p.id in source.freshness_policies.values()
                for p in self.policies
            ):
                raise ValueError("Download time cannot establish observation freshness")
        aliases = [a.casefold().strip() for t in self.territories for a in (t.name, *t.aliases)]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Ambiguous territory alias")
        return self


class Period(Contract):
    start: AwareDatetime
    end: AwareDatetime
    kind: Literal["observation_interval", "snapshot_window"] = "observation_interval"

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start > self.end:
            raise ValueError("Invalid period")
        return self


class CoverageQuery(Contract):
    territory: Key | None = None
    aoi: Bounds | None = None
    categories: tuple[Key, ...] = Field(min_length=1, max_length=10)
    period: Period | None = None
    mode: DataMode = "real"
    purpose: Literal["local_analysis", "redistribution"] = "local_analysis"

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Duplicate categories")
        return self


class AcquisitionOption(Contract):
    source_id: Key
    acquirability: Acquirability
    reason: Key
    network_permission: Literal["permitted", "review_required", "forbidden"]
    availability: Literal["ready", "degraded", "unavailable", "not_integrated", "unknown"]
    potentially_available: bool
    adapter_status: Literal["ready", "not_integrated"]
    license_status: Literal["verified_local_use", "review_required", "forbidden"]
    local_use_permitted: bool
    automatic_acquisition_implemented: bool = False


class DatasetReference(Contract):
    """Projection of existing metadata, without ambiguous legacy date/stale aliases."""

    provider: ProviderId
    slug: Slug
    revision: str
    data_version: Version
    active: bool
    bbox: Bounds
    origin: DataOrigin
    source_name: str
    license: str
    attribution: str
    limitations: tuple[str, ...]


class DatasetCoverage(Contract):
    metadata: DatasetReference
    spatial_fit: Literal["full_for_requested_scope", "partial", "unknown"]
    freshness: Freshness
    freshness_policy: Key
    freshness_basis: Literal["source_timestamp", "period_end", "generated_at", "unknown"]
    observed_at: AwareDatetime | None = None
    source_timestamp: AwareDatetime | None = None
    published_at: AwareDatetime | None = None
    fetched_at: AwareDatetime | None = None
    generated_at: AwareDatetime | None = None
    imported_at: AwareDatetime | None = None
    temporal_coverage: Period | None = None
    next_update_at: AwareDatetime | None = None
    temporal_fit: Literal["snapshot_in_period", "outside_period", "unknown"]
    usable: bool
    reasons: tuple[Key, ...]


class CoverageAssessment(Contract):
    category: Key
    local_status: LocalState
    summary: Literal[
        "usable",
        "stale",
        "partial",
        "acquirable",
        "source_unavailable",
        "not_available_from_approved_sources",
        "unknown",
    ]
    availability: Literal["present", "missing", "unknown"]
    freshness: Freshness
    completeness: Literal["full_for_requested_scope", "partial", "unknown"]
    object_quality: Literal["unknown", "not_applicable"] = "unknown"
    datasets: tuple[DatasetCoverage, ...]
    acquisition: tuple[AcquisitionOption, ...]
    reasons: tuple[Key, ...]


class CoverageResult(Contract):
    schema_version: Literal["coverage-v2"] = "coverage-v2"
    registry_revision: Key
    config_sha256: Version
    evaluated_at: AwareDatetime
    query: CoverageQuery
    assessments: tuple[CoverageAssessment, ...]
    metadata_complete: bool
    limitations: tuple[Text, ...]


class DataRequirement(Contract):
    id: Key
    category: Key
    required: bool = True
    allow_partial: bool = False
    accepted_origins: tuple[DataOrigin, ...] = (DataOrigin.OPEN_DATA, DataOrigin.LICENSED)
    require_known_quality: bool = False
    allow_assumption: bool = False
    critical_for: tuple[Key, ...] = Field(default=("analysis",), min_length=1, max_length=10)


class SufficiencyDecision(Contract):
    requirement_id: Key
    state: Literal["sufficient", "partial", "missing", "stale", "unknown"]
    action: Literal[
        "use_pinned",
        "cache_revalidate",
        "request_acquisition",
        "ask_user",
        "omit_optional",
        "block",
    ]
    technically_eligible: bool
    quality: Literal["unknown", "not_applicable"]
    reasons: tuple[Key, ...]


class SufficiencyAssessment(Contract):
    """Technical data eligibility only, never tool authorization or business confidence."""

    requirements_revision: Key
    evaluated_at: AwareDatetime
    decisions: tuple[SufficiencyDecision, ...]
    allowed_tasks: tuple[Key, ...]
    blocked_tasks: tuple[Key, ...]
    warnings: tuple[Key, ...] = ("technical_eligibility_is_not_business_validity",)

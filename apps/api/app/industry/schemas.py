from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.api.conversation_schemas import ConversationView
from app.api.schemas import BusinessProfile, Contract
from app.data.registry_schemas import CoverageResult, SufficiencyAssessment
from app.domain.enums import DataOrigin
from app.finance.schemas import Amount, Sales
from app.limits.config import VersionNumber

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Scalar = (
    Text
    | Annotated[int, Field(strict=True, ge=0, le=1000000)]
    | Annotated[bool, Field(strict=True)]
)


class ProfileValue(Contract):
    value: Scalar
    unit: str
    origin: DataOrigin = DataOrigin.USER_INPUT
    epistemic: Literal["user_provided", "derived", "assumed"] = "user_provided"
    review: Literal["proposed", "confirmed"] = "proposed"
    evidence: Text
    lineage: Literal["user_message", "user_edit", "legacy_v1", "classification"]

    @model_validator(mode="after")
    def provenance(self) -> Self:
        if self.epistemic == "assumed" and self.origin != DataOrigin.SYNTHETIC:
            raise ValueError("An assumption is never an observation")
        if self.epistemic == "user_provided" and self.origin != DataOrigin.USER_INPUT:
            raise ValueError("User confirmation does not create a source observation")
        return self


class UniversalProfile(Contract):
    schema_version: Literal["business-profile-v2"] = "business-profile-v2"
    id: UUID
    conversation_id: UUID
    revision: VersionNumber
    idea: str = Field(default="", max_length=1600)
    industry: Key = "generic"
    raw_industry: Text | None = None
    resolution: Literal["known", "unknown", "ambiguous"] = "unknown"
    industry_evidence: Text | None = None
    config_version: str = "u04-v1"
    config_sha256: str | None = None
    configuration_snapshot: IndustryDefinition | None = None
    values: dict[Key, ProfileValue] = Field(default_factory=dict, max_length=20)
    extensions: dict[Key, dict[Key, ProfileValue]] = Field(default_factory=dict, max_length=8)
    confirmed_revision: VersionNumber | None = None
    deferred_fields: tuple[Key, ...] = Field(default=(), max_length=20)
    legacy_snapshot: BusinessProfile


class FieldDefinition(Contract):
    id: Key
    label: Text
    question: Text
    kind: Literal["text", "money", "integer", "ratio", "boolean", "choice"] = "text"
    unit: str = "text"
    choices: tuple[Text, ...] = ()
    maximum: int = 1000000
    driver: Literal["revenue", "fixed_cost", "variable_cost", "capacity", "context"] = "context"


class IndustryDefinition(Contract):
    id: Key
    label: Text
    version: str = "u04-v1"
    aliases: tuple[Text, ...]
    business_models: tuple[Text, ...]
    required: tuple[Key, ...]
    fields: tuple[FieldDefinition, ...]
    data_categories: tuple[str, ...]
    optional_categories: tuple[str, ...] = ()
    geo_policy: Literal["required", "optional", "none"]
    geo_adapter: Literal["coffee_poi_v1"] | None = None
    finance_adapter: Literal["coffee_finance_v1"] | None = None
    limitations: tuple[Text, ...]


class FieldUpdate(Contract):
    field: Key
    value: Scalar | None


class ExtractedUpdate(FieldUpdate):
    evidence: Text


class IndustryProposal(Contract):
    industry: Key | None = None
    raw_industry: Text | None = None
    industry_evidence: Text | None = None
    resolution: Literal["known", "unknown", "ambiguous"] = "unknown"
    updates: tuple[ExtractedUpdate, ...] = Field(default=(), max_length=14)
    clarification: Key | None = None
    capabilities: tuple[str, ...] = Field(default=(), max_length=4)


class UniversalPatch(Contract):
    expected_version: VersionNumber
    industry: Key | None = None
    raw_industry: Text | None = None
    updates: tuple[FieldUpdate, ...] = Field(default=(), max_length=20)
    defer_fields: tuple[Key, ...] = Field(default=(), max_length=20)


class IndustryCatalog(Contract):
    enabled: bool
    finance_v2_enabled: bool = False
    revision: str = "u04-v1"
    industries: tuple[IndustryDefinition, ...]


class UniversalMessage(Contract):
    expected_version: VersionNumber
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)]


class CapabilityDecision(Contract):
    id: str
    status: Literal[
        "available", "partial", "unavailable", "unsupported", "not_required", "needs_confirmation"
    ]
    method: str | None = None
    reason: str


class AdaptivePlan(Contract):
    profile_revision: int
    industry_version: str
    outcome: Literal["collecting", "ready", "partial"]
    missing_fields: tuple[str, ...]
    next_question: str | None
    geo_required: bool | None
    capabilities: tuple[CapabilityDecision, ...]
    stages: tuple[
        Literal["clarify", "confirm", "location", "finance", "banking", "partial_result"], ...
    ]
    coverage: CoverageResult | None = None
    sufficiency: SufficiencyAssessment | None = None


class CoffeeDriverInputs(Contract):
    average_check: Amount | None = None
    sales_per_day: Sales | None = None


class UniversalView(Contract):
    conversation: ConversationView
    profile: UniversalProfile
    configuration: IndustryDefinition
    field_definitions: tuple[FieldDefinition, ...]
    plan: AdaptivePlan
    coffee_inputs: CoffeeDriverInputs | None = None
    extraction: Literal["none", "ollama", "clarification_fallback"] = "none"

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.domain.enums import Confidence, ConfirmationState, DataOrigin, Funding

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2, allow_inf_nan=False)]
MetricValue = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BusinessPreferences(Contract):
    format: NonEmptyText | None = None
    preferred_districts: tuple[NonEmptyText, ...] = ()
    constraints: tuple[NonEmptyText, ...] = ()


class BusinessProfile(Contract):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    city: NonEmptyText | None = None
    category: NonEmptyText | None = None
    budget: Money | None = None
    funding: Funding | None = None
    preferences: BusinessPreferences = Field(default_factory=BusinessPreferences)
    confirmation_state: ConfirmationState = ConfirmationState.DRAFT


class MetricWithProvenance(Contract):
    metric: NonEmptyText
    value: MetricValue
    unit: NonEmptyText
    origin: DataOrigin
    source_name: NonEmptyText
    observed_at: AwareDatetime | None
    generated_at: AwareDatetime
    data_version: NonEmptyText
    confidence: Confidence
    limitations: tuple[NonEmptyText, ...]

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        if self.observed_at is not None and self.observed_at > self.generated_at:
            raise ValueError("observed_at must not be later than generated_at")
        if self.origin == DataOrigin.SYNTHETIC:
            if self.confidence != Confidence.NOT_APPLICABLE:
                raise ValueError("synthetic data must use confidence=not_applicable")
            if not self.limitations:
                raise ValueError("synthetic data must declare limitations")
        return self


class AnalysisRun(Contract):
    id: UUID = Field(default_factory=uuid4)
    profile_snapshot: BusinessProfile
    dataset_versions: dict[NonEmptyText, NonEmptyText] = Field(min_length=1)
    algorithm_version: NonEmptyText
    tool_trace_id: UUID
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

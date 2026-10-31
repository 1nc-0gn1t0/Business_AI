from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.api.schemas import Contract
from app.finance.schemas import InputSource, exact_decimal
from app.industry.schemas import Key, UniversalProfile
from app.limits.config import VersionNumber

Number = Annotated[
    Decimal, Field(ge=0, le=1000000000000, max_digits=19, decimal_places=6, allow_inf_nan=False)
]
ModelId = Literal["auto_repair", "online_school", "generic"]
Billing = Literal["monthly", "subscription", "course"]
Name = Literal["conservative", "base", "optimistic"]


class Range(Contract):
    base: Number
    low: Number
    high: Number
    _exact = field_validator("base", "low", "high", mode="before")(exact_decimal)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if not self.low <= self.base <= self.high:
            raise ValueError("Expected low <= base <= high")
        return self


class FinancialParameter(Contract):
    id: Key
    label: str
    unit: str
    minimum: Decimal = Decimal(0)
    maximum: Decimal = Decimal("1000000000")
    integer: bool = False
    direction: Literal["revenue", "cost", "context"]


class FinancialDefinition(Contract):
    id: ModelId
    version: str = "u05-decimal-v1"
    parameters: tuple[FinancialParameter, ...]
    limitations: tuple[str, ...]


class FinancialInput(Range):
    unit: str
    source: InputSource
    epistemic: Literal["user_provided", "assumed"]
    review: Literal["proposed", "confirmed", "rejected"] = "proposed"
    method: Literal["profile_v2", "user_input", "qwen_exploratory", "user_assumption"]
    basis: str = Field(min_length=1, max_length=300)
    revision: int
    created_at: datetime
    generation_model: str | None = None
    generation_prompt_version: str | None = None

    @model_validator(mode="after")
    def origin_rules(self) -> Self:
        expected = "synthetic" if self.epistemic == "assumed" else "user_input"
        if self.source.origin.value != expected:
            raise ValueError("Confirmation cannot change epistemic origin")
        return self


class ParameterUpdate(Range):
    parameter: Key
    unit: str = Field(max_length=64)
    kind: Literal["user_input", "user_assumption"] = "user_input"
    basis: str = Field(default="Вводная пользователя", min_length=1, max_length=300)


class Assumption(Range):
    parameter: Key
    unit: str = Field(max_length=64)
    basis: str = Field(min_length=1, max_length=160)
    epistemic: Literal["assumed"] = "assumed"
    source: Literal["exploratory_no_market_evidence"] = "exploratory_no_market_evidence"


class AssumptionProposal(Contract):
    model: ModelId
    assumptions: tuple[Assumption, ...] = Field(max_length=8)


class FinancialCommand(Contract):
    request_id: UUID
    expected_profile_revision: VersionNumber
    expected_input_revision: VersionNumber


class InputPatch(FinancialCommand):
    updates: tuple[ParameterUpdate, ...] = Field(default=(), max_length=24)
    billing_model: Billing | None = None
    reset_for_profile: bool = False


class ReviewCommand(FinancialCommand):
    confirm: tuple[Key, ...] = Field(default=(), max_length=24)
    reject: tuple[Key, ...] = Field(default=(), max_length=24)


class FinancialDocument(Contract):
    profile_revision: int
    profile_config_sha256: str
    model: ModelId
    adapter_version: str = "u05-decimal-v1"
    adapter_sha256: str = ""
    revision: int = 0
    billing_model: Billing | None = None
    entries: dict[Key, FinancialInput] = Field(default_factory=dict, max_length=24)


class BreakEven(Contract):
    status: Literal["calculated", "nonpositive_margin", "above_capacity", "unavailable"]
    units: Decimal | None = None
    revenue: Decimal | None = None
    capacity_utilization: Decimal | None = None


class FinancialScenario(Contract):
    name: Name
    drivers: dict[str, Decimal]
    period: Literal["month", "course_cohort"]
    months: Decimal
    units: Decimal
    volume_unit: Literal["orders", "students", "units"]
    capacity: Decimal | None
    revenue: Decimal
    variable_costs: Decimal
    fixed_costs: Decimal
    contribution: Decimal
    operating_result: Decimal
    contribution_per_unit: Decimal
    capacity_utilization: Decimal | None
    safety_margin_ratio: Decimal | None
    break_even: BreakEven


class FinancialSensitivity(Contract):
    parameter: str
    unit: str
    value: Decimal
    status: Literal["calculated", "outside_domain"]
    operating_result: Decimal | None
    difference_from_base: Decimal | None


class FinancialCalculation(Contract):
    status: Literal["calculated", "partial"]
    missing: tuple[str, ...]
    scenarios: tuple[FinancialScenario, ...] = ()
    sensitivity: tuple[FinancialSensitivity, ...] = ()
    origin: Literal["modelled"] = "modelled"
    currency: Literal["RUB"] = "RUB"
    contains_assumptions: bool
    formulas: dict[str, str]
    metric_inputs: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    limitations: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    rounding: str = "Decimal precision 64 / HALF_UP; RUB rounded to kopecks before subtraction"


class FinancialSnapshot(Contract):
    id: UUID
    created_at: datetime
    fingerprint: str
    profile: UniversalProfile
    inputs: FinancialDocument
    configuration: FinancialDefinition
    result: FinancialCalculation


class FinancialOperation(Contract):
    request_id: UUID
    kind: Literal["propose", "calculate"]
    state: Literal["running", "completed", "failed", "interrupted", "cancelled"]
    profile_revision: int
    input_revision: int
    created_at: datetime
    deadline_at: datetime
    error_code: str | None = None


class FinancialView(Contract):
    enabled: bool = True
    profile_revision: int = 0
    configuration: FinancialDefinition
    document: FinancialDocument
    current: bool
    missing: tuple[str, ...]
    needs_review: tuple[str, ...]
    result: FinancialSnapshot | None = None
    proposal_status: Literal[
        "idle", "running", "completed", "failed", "interrupted", "cancelled"
    ] = "idle"
    proposal_error: str | None = None
    operation: FinancialOperation | None = None


class WhatIf(FinancialCommand):
    updates: tuple[ParameterUpdate, ...] = Field(min_length=1, max_length=24)


class WhatIfResult(Contract):
    persisted: Literal[False] = False
    input_revision: int
    result: FinancialCalculation

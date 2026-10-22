from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.api.schemas import BusinessProfile, Contract, Money, NonEmptyText
from app.domain.enums import Confidence, DataOrigin
from app.geo.candidate_schemas import Version
from app.geo.schemas import Slug

ScenarioName = Literal["conservative", "base", "optimistic"]
Driver = Literal["average_check", "sales_per_day", "rent", "variable_cost_ratio"]
MetricName = Literal[
    "monthly_sales",
    "monthly_revenue",
    "monthly_variable_cost",
    "monthly_fixed_cost",
    "contribution_per_sale_exact",
    "contribution_per_sale",
    "monthly_contribution",
    "operating_result",
    "break_even_sales_per_day",
]
Change = Annotated[Decimal, Field(gt=-1, le=1, max_digits=5, decimal_places=4, allow_inf_nan=False)]


class InputSource(Contract):
    origin: DataOrigin
    source_name: NonEmptyText
    data_version: NonEmptyText
    confidence: Confidence
    limitations: tuple[NonEmptyText, ...] = Field(min_length=1, max_length=10)
    observed_at: AwareDatetime | None = None
    evidence_ref: NonEmptyText | None = None
    source_attested: bool = False

    @model_validator(mode="after")
    def provenance_rules(self) -> Self:
        if self.origin == DataOrigin.SYNTHETIC and self.confidence != Confidence.NOT_APPLICABLE:
            raise ValueError("Synthetic assumptions require confidence=not_applicable")
        if self.origin in (DataOrigin.OPEN_DATA, DataOrigin.LICENSED, DataOrigin.BANK_INTERNAL):
            if not self.source_attested or not self.evidence_ref or self.observed_at is None:
                raise ValueError("Documented facts require source attestation, evidence and date")
        elif self.source_attested:
            raise ValueError("Assumptions/user input cannot be attested as documented facts")
        return self


def exact_decimal(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError("Send decimal values as strings or integers, not binary floats/booleans")
    return value


class Amount(Contract):
    value: Money
    source: InputSource
    _exact = field_validator("value", mode="before")(exact_decimal)


class Ratio(Amount):
    value: Annotated[
        Decimal, Field(ge=0, lt=1, max_digits=7, decimal_places=6, allow_inf_nan=False)
    ]


class Sales(Contract):
    value: int = Field(strict=True, ge=0, le=1000000)
    source: InputSource


class WorkingDays(Sales):
    value: int = Field(strict=True, ge=1, le=31)


class StartupCosts(Contract):
    equipment: Amount
    renovation: Amount
    rent_deposit: Amount
    initial_inventory: Amount
    registration: Amount
    other: Amount
    working_capital_reserve: Amount


class FixedCosts(Contract):
    rent: Amount
    payroll: Amount
    utilities: Amount
    other: Amount


class ScenarioInputs(Contract):
    average_check: Amount
    sales_per_day: Sales
    variable_cost_ratio: Ratio
    fixed_costs: FixedCosts | None = None

    @model_validator(mode="after")
    def positive_check(self) -> Self:
        if self.average_check.value <= 0:
            raise ValueError("average_check must be positive")
        return self


class Scenarios(Contract):
    conservative: ScenarioInputs
    base: ScenarioInputs
    optimistic: ScenarioInputs


class ZoneReference(Contract):
    dataset_slug: Slug
    data_version: Version
    candidate_id: Version
    ranking_fingerprint: Version


class FinanceRequest(Contract):
    profile: BusinessProfile
    startup: StartupCosts
    monthly_fixed_costs: FixedCosts
    working_days_per_month: WorkingDays
    scenarios: Scenarios
    selected_zone: ZoneReference | None = None
    sensitivity_changes: tuple[Change, ...] = Field(min_length=1, max_length=6)

    @field_validator("sensitivity_changes", mode="before")
    @classmethod
    def exact_changes(cls, values: object) -> object:
        if isinstance(values, (list, tuple)):
            for value in values:
                exact_decimal(value)
        return values

    @model_validator(mode="after")
    def unique_changes(self) -> Self:
        if len(set(self.sensitivity_changes)) != len(self.sensitivity_changes) or (
            Decimal(0) in self.sensitivity_changes
        ):
            raise ValueError("Sensitivity changes must be nonzero and unique")
        return self


class FinancialMetric(Contract):
    value: Decimal = Field(allow_inf_nan=False)
    unit: Literal["RUB", "RUB/sale", "sales/month", "sales/day"]
    origin: Literal["modelled"] = "modelled"
    confidence: Literal["low"] = "low"
    algorithm_version: str
    formula_id: MetricName
    input_paths: tuple[str, ...]


class ScenarioResult(Contract):
    name: ScenarioName
    inputs: ScenarioInputs
    metrics: dict[MetricName, FinancialMetric]
    warnings: tuple[str, ...]


class BudgetComparison(Contract):
    status: Literal["within_model_budget", "model_budget_shortfall", "budget_unknown"]
    budget: Decimal | None
    budget_origin: Literal["user_input"] = "user_input"
    startup_required: Decimal
    remaining: Decimal | None
    funding_gap: Decimal | None
    origin: Literal["modelled"] = "modelled"
    limitations: tuple[str, ...]


class StartupResult(Contract):
    items: StartupCosts
    launch_uses_excluding_reserve: Decimal
    working_capital_reserve: Decimal
    total_initial_funding: Decimal
    origin: Literal["modelled"] = "modelled"
    formula: str


class SensitivityPoint(Contract):
    driver: Driver
    relative_change: Decimal
    actual_value: Decimal
    status: Literal["calculated", "outside_domain"]
    operating_result: Decimal | None
    difference_from_base: Decimal | None
    break_even_sales_per_day: Decimal | None
    origin: Literal["modelled"] = "modelled"
    explanation: str


class ScenarioComparison(Contract):
    scenario: ScenarioName
    revenue_difference_from_base: Decimal
    operating_result_difference_from_base: Decimal


class FinanceResult(Contract):
    status: Literal["calculated"] = "calculated"
    algorithm_version: str
    request_fingerprint: str
    request_snapshot: FinanceRequest
    currency: Literal["RUB"] = "RUB"
    rounding: str
    startup: StartupResult
    budget: BudgetComparison
    scenarios: tuple[ScenarioResult, ...]
    comparison: tuple[ScenarioComparison, ...]
    sensitivity: tuple[SensitivityPoint, ...]
    formulas: dict[MetricName, str]
    missing_data: tuple[str, ...]
    limitations: tuple[str, ...]
    warnings: tuple[str, ...]
    zone_reference_status: Literal["not_provided", "not_verified_by_finance_service"]

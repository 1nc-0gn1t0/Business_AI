from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StringConstraints, model_validator

from app.api.schemas import BusinessProfile, Contract

Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,99}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Category = Literal[
    "settlement",
    "registration",
    "merchant_acquiring",
    "internet_acquiring",
    "business_card",
    "financing_information",
]
NeedField = Literal[
    "launch_stage",
    "registration_status",
    "sales_channel",
    "needs_settlement_account",
    "needs_registration_help",
    "accepts_card_payments",
    "needs_expense_card",
    "financing_interest",
]
ALLOWED: dict[str, tuple[str | bool, ...]] = {
    "launch_stage": ("idea", "preparing", "operating"),
    "registration_status": ("not_registered", "ip", "legal_entity"),
    "sales_channel": ("offline", "online", "both"),
    **dict.fromkeys(
        (
            "needs_settlement_account",
            "needs_registration_help",
            "accepts_card_payments",
            "needs_expense_card",
            "financing_interest",
        ),
        (True, False),
    ),
}


class BankingNeeds(Contract):
    launch_stage: Literal["idea", "preparing", "operating"] | None = None
    registration_status: Literal["not_registered", "ip", "legal_entity"] | None = None
    sales_channel: Literal["offline", "online", "both"] | None = None
    needs_settlement_account: StrictBool | None = None
    needs_registration_help: StrictBool | None = None
    accepts_card_payments: StrictBool | None = None
    needs_expense_card: StrictBool | None = None
    financing_interest: StrictBool | None = None


class EvidenceSource(Contract):
    id: Key
    url: Annotated[
        str, StringConstraints(pattern=r"^https://(?:www\.)?(?:vtb\.ru|vtbrussia\.ru)/[^\s]*$")
    ]
    title: Text
    reviewed_at: date
    verification: Literal["verified", "cached_only", "unavailable"]
    last_verified_at: date | None = None
    content_sha256: Digest | None = None
    summary: Text
    limitations: tuple[Text, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def verified_evidence(self) -> Self:
        if self.verification == "verified" and (
            self.last_verified_at is None or self.content_sha256 is None
        ):
            raise ValueError("Verified sources require a direct review date and content digest")
        if self.last_verified_at is not None and self.last_verified_at > self.reviewed_at:
            raise ValueError("Verification cannot follow the last review")
        return self


class EligibilityRule(Contract):
    id: Key
    field: NeedField
    one_of: tuple[str | StrictBool, ...] = Field(min_length=1, max_length=3)
    explanation: Text
    question: Text
    origin: Literal["application_policy"] = "application_policy"
    purpose: Literal["relevance_only_not_bank_eligibility"] = "relevance_only_not_bank_eligibility"

    @model_validator(mode="after")
    def valid_domain(self) -> Self:
        allowed = ALLOWED[self.field]
        if len(set(self.one_of)) != len(self.one_of) or any(
            not any(type(value) is type(item) and value == item for item in allowed)
            for value in self.one_of
        ):
            raise ValueError("Rule values must belong to the declared field domain")
        return self


class Product(Contract):
    id: Key
    version: Key
    name: Text
    category: Category
    description: Text
    mode: Literal["public_reference", "demonstration"]
    status: Literal["published", "unconfirmed", "unavailable", "retired"]
    last_reviewed_at: date
    source_ids: tuple[Key, ...] = Field(min_length=1)
    rules: tuple[EligibilityRule, ...] = Field(min_length=1, max_length=10)
    applicable_conditions: tuple[Text, ...] = Field(min_length=1)
    unknown_conditions: tuple[Text, ...] = Field(min_length=1)
    limitations: tuple[Text, ...] = Field(min_length=1)


class Catalogue(Contract):
    version: Key
    review_window_days: int = Field(ge=1, le=90)
    sources: tuple[EvidenceSource, ...]
    products: tuple[Product, ...]

    @model_validator(mode="after")
    def unique_references(self) -> Self:
        ids = {s.id for s in self.sources}
        if len(ids) != len(self.sources) or len({p.id for p in self.products}) != len(
            self.products
        ):
            raise ValueError("Catalogue IDs must be unique")
        for product in self.products:
            if (
                not set(product.source_ids) <= ids
                or len(set(product.source_ids)) != len(product.source_ids)
                or len({r.id for r in product.rules}) != len(product.rules)
            ):
                raise ValueError("Product references and rule IDs must be valid and unique")
        return self


class ProductView(Contract):
    product: Product
    sources: tuple[EvidenceSource, ...]
    availability: Literal["verified_reference", "demonstration_only", "blocked"]
    availability_reasons: tuple[Text, ...]


class CatalogueView(Contract):
    version: str
    fingerprint: Digest
    as_of: date
    review_window_days: int
    products: tuple[ProductView, ...]
    limitations: tuple[str, ...]


class MatchRequest(Contract):
    expected_version: int = Field(strict=True, ge=0)
    needs: BankingNeeds = Field(default_factory=BankingNeeds)
    catalogue_fingerprint: Digest | None = None


class RuleEvaluation(Contract):
    rule: EligibilityRule
    status: Literal["matched", "unknown", "not_matched"]
    actual_value: str | StrictBool | None
    evaluated_value: str | StrictBool | None
    input_path: str
    input_origin: Literal["user_input"] = "user_input"


class ProductDecision(Contract):
    entry: ProductView
    status: Literal[
        "potential_match",
        "information_only",
        "demo_match",
        "demo_information",
        "needs_clarification",
        "not_matched",
        "unavailable",
    ]
    reasons: tuple[str, ...]
    evaluations: tuple[RuleEvaluation, ...]
    missing_fields: tuple[NeedField, ...]


class MatchResult(Contract):
    status: Literal["evaluated", "needs_confirmation", "catalogue_unavailable"]
    algorithm_version: str
    catalogue: CatalogueView
    request_fingerprint: Digest
    profile_snapshot: BusinessProfile
    profile_version: int
    needs_snapshot: BankingNeeds
    decisions: tuple[ProductDecision, ...]
    recommended_ids: tuple[str, ...]
    demonstration_ids: tuple[str, ...]
    missing_fields: tuple[NeedField, ...]
    credit_decision: Literal["not_assessed"] = "not_assessed"
    limitations: tuple[str, ...]

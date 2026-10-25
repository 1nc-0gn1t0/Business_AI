from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from app.api.schemas import BusinessProfile, Contract, Money
from app.bank.schemas import Digest, Key, ProductView
from app.domain.enums import Funding
from app.limits.config import VersionNumber, policy

Purpose = Literal["assistant", "marketing", "demo_lead"]
Revision = VersionNumber
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
RECEIPT_MESSAGE: Literal["Демонстрационная заявка создана. Данные в ВТБ не отправлены"] = (
    "Демонстрационная заявка создана. Данные в ВТБ не отправлены"
)


class ConsentText(Contract):
    purpose: Purpose
    version: str
    title: str
    text: str
    recipient: str = "Business AI (локальный демонстрационный сервис); ВТБ данные не получает"
    legally_approved: Literal[False] = False


class ConsentDecision(Contract):
    expected_revision: Revision
    text_version: Annotated[str, StringConstraints(min_length=1, max_length=policy().profile_chars)]
    decision: Literal["grant", "decline", "withdraw"]


class ConsentView(Contract):
    id: UUID | None = None
    purpose: Purpose
    revision: Revision = 0
    text_version: str
    status: Literal["not_given", "granted", "declined", "withdrawn"] = "not_given"
    given_at: AwareDatetime | None = None
    withdrawn_at: AwareDatetime | None = None
    recorded_at: AwareDatetime | None = None
    text_snapshot: ConsentText | None = None


class ConsentState(Contract):
    texts: tuple[ConsentText, ...]
    consents: tuple[ConsentView, ...]


class LeadFields(Contract):
    city: ShortText
    category: ShortText
    budget: Money | None = None
    funding: Funding | None = None
    format: ShortText | None = None


class DraftInput(Contract):
    expected_profile_version: Revision
    catalogue_fingerprint: Digest
    product_ids: tuple[Key, ...] = Field(min_length=1, max_length=6)
    fields: LeadFields

    @model_validator(mode="after")
    def unique_products(self) -> "DraftInput":
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("Product IDs must be unique")
        return self


class DraftEdit(DraftInput):
    expected_revision: Revision


class DraftAction(Contract):
    expected_revision: Revision
    confirmed: Literal[True]
    payload_fingerprint: Digest

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_boolean(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit JSON true is required")
        return value


class SubmitRequest(DraftAction):
    idempotency_key: UUID


class LeadPayload(Contract):
    mode: Literal["demonstration"] = "demonstration"
    recipient: Literal["local_mock_only"] = "local_mock_only"
    fields: LeadFields
    products: tuple[ProductView, ...]
    catalogue_version: str
    catalogue_fingerprint: Digest
    field_origins: dict[str, Literal["confirmed_profile", "draft_user_input"]]


class LeadDraft(Contract):
    id: UUID
    revision: Revision
    profile_version: Revision
    profile_snapshot: BusinessProfile
    consents: tuple[ConsentView, ...]
    payload: LeadPayload
    payload_fingerprint: Digest
    state: Literal["draft", "confirmed", "submitted"]
    stale: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime
    confirmed_at: AwareDatetime | None = None


class LeadReceipt(Contract):
    id: UUID
    draft_id: UUID
    draft_revision: Revision
    profile_version: Revision
    payload_fingerprint: Digest
    payload: LeadPayload
    consents: tuple[ConsentView, ...]
    created_at: AwareDatetime
    status: Literal["demo_created"] = "demo_created"
    sent_to_bank: Literal[False] = False
    message: Literal["Демонстрационная заявка создана. Данные в ВТБ не отправлены"] = (
        RECEIPT_MESSAGE
    )


class AuditView(Contract):
    id: UUID
    action: str
    object_id: UUID
    created_at: AwareDatetime
    outcome: Literal["recorded"] = "recorded"
    actor: Literal["guest_session"] = "guest_session"


class LeadWorkspace(Contract):
    drafts: tuple[LeadDraft, ...]
    receipts: tuple[LeadReceipt, ...]

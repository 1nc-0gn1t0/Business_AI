from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.api.schemas import BusinessProfile, Contract, Money
from app.domain.enums import ConversationState, Funding, MessageRole

ProfileText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Version = Annotated[int, Field(strict=True, ge=0)]


class PreferencesPatch(Contract):
    format: ProfileText | None = None
    preferred_districts: tuple[ProfileText, ...] = Field(default=(), max_length=20)
    constraints: tuple[ProfileText, ...] = Field(default=(), max_length=20)


class ProfilePatch(Contract):
    city: ProfileText | None = None
    category: ProfileText | None = None
    budget: Money | None = None
    funding: Funding | None = None
    preferences: PreferencesPatch | None = None


class MessageRequest(Contract):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    expected_version: Version


class PatchRequest(Contract):
    patch: ProfilePatch
    expected_version: Version


class ConfirmRequest(Contract):
    expected_version: Version


class ConversationView(Contract):
    id: UUID
    version: int
    state: ConversationState
    profile: BusinessProfile
    missing_fields: tuple[str, ...]
    assistant_message: str
    extraction_mode: Literal["rules", "stub", "ollama"] = "rules"
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ConversationCreated(ConversationView):
    access_token: str


class MessageView(Contract):
    id: UUID
    version: int
    role: MessageRole
    content: str
    created_at: AwareDatetime


class RevisionView(Contract):
    version: int
    source: str
    profile: BusinessProfile
    created_at: AwareDatetime

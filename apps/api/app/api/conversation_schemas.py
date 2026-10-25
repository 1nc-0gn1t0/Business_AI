from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.api.schemas import BusinessProfile, Contract, Money, ProfileText
from app.domain.enums import ConversationState, Funding, MessageRole
from app.limits.config import VersionNumber, policy

Version = VersionNumber


class PreferencesPatch(Contract):
    format: ProfileText | None = None
    preferred_districts: tuple[ProfileText, ...] = Field(
        default=(), max_length=policy().profile_items
    )
    constraints: tuple[ProfileText, ...] = Field(default=(), max_length=policy().profile_items)


class ProfilePatch(Contract):
    city: ProfileText | None = None
    category: ProfileText | None = None
    budget: Money | None = None
    funding: Funding | None = None
    preferences: PreferencesPatch | None = None


class MessageRequest(Contract):
    content: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=policy().message_chars),
    ]
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

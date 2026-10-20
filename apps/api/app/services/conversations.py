import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.conversation_schemas import (
    ConversationCreated,
    ConversationView,
    MessageView,
    ProfilePatch,
    RevisionView,
)
from app.api.schemas import BusinessProfile
from app.db.models import (
    BusinessProfileRecord,
    ConversationRecord,
    MessageRecord,
    ProfileRevisionRecord,
)
from app.domain.conversation import (
    CONFIRMATIONS,
    apply_patch,
    confirm,
    extract_business_profile,
    missing_fields,
    reply_for,
    state_for,
)
from app.domain.enums import ConversationState, MessageRole


class ConversationNotFound(Exception):
    pass


class VersionConflict(Exception):
    def __init__(self, version: int):
        self.version = version


class IncompleteProfile(Exception):
    def __init__(self, missing: tuple[str, ...]):
        self.missing = missing


class Conversations:
    def __init__(self, session: Session):
        self.session = session

    def _authorise(
        self, conversation_id: UUID, token: str, *, lock: bool = False
    ) -> ConversationRecord:
        query = sa.select(ConversationRecord).where(ConversationRecord.id == conversation_id)
        if lock:
            query = query.with_for_update()
        record = self.session.scalar(query)
        digest = hashlib.sha256(token.encode()).hexdigest()
        if record is None or not hmac.compare_digest(record.token_hash, digest):
            raise ConversationNotFound
        return record

    def _profile(self, conversation_id: UUID) -> BusinessProfile:
        record = self.session.scalar(
            sa.select(BusinessProfileRecord).where(
                BusinessProfileRecord.conversation_id == conversation_id
            )
        )
        if record is None:
            raise ConversationNotFound
        return BusinessProfile.model_validate(
            {key: getattr(record, key) for key in BusinessProfile.model_fields}
        )

    def _view(self, record: ConversationRecord) -> ConversationView:
        profile = self._profile(record.id)
        return ConversationView(
            id=record.id,
            version=record.version,
            state=state_for(profile),
            profile=profile,
            missing_fields=missing_fields(profile),
            assistant_message=reply_for(profile),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def create(self) -> ConversationCreated:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        record = ConversationRecord(
            id=uuid4(),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            state=ConversationState.COLLECTING,
            version=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        self.session.flush()
        profile = BusinessProfile(conversation_id=record.id)
        self.session.add(BusinessProfileRecord(**profile.model_dump()))
        self._save_event(record, profile, "created")
        self.session.flush()
        return ConversationCreated(**self._view(record).model_dump(), access_token=token)

    def get(self, conversation_id: UUID, token: str) -> ConversationView:
        return self._view(self._authorise(conversation_id, token))

    def _save_event(
        self, record: ConversationRecord, profile: BusinessProfile, source: str
    ) -> None:
        self.session.add(
            ProfileRevisionRecord(
                conversation_id=record.id,
                version=record.version,
                source=source,
                profile_snapshot=profile.model_dump(mode="json"),
                created_at=record.updated_at,
            )
        )
        self.session.add(
            MessageRecord(
                conversation_id=record.id,
                version=record.version,
                role=MessageRole.ASSISTANT,
                content=reply_for(profile),
                created_at=record.updated_at,
            )
        )

    def update(
        self,
        conversation_id: UUID,
        token: str,
        expected_version: int,
        *,
        content: str | None = None,
        patch: ProfilePatch | None = None,
        confirmation: bool = False,
    ) -> ConversationView:
        record = self._authorise(conversation_id, token, lock=True)
        if record.version != expected_version:
            raise VersionConflict(record.version)
        profile = self._profile(record.id)
        source = "patch"
        if content is not None:
            source = "message"
            if content.casefold().strip(" .!") in CONFIRMATIONS and not missing_fields(profile):
                confirmation = True
            else:
                patch = extract_business_profile(content, profile)
        if patch is not None:
            profile = apply_patch(profile, patch)
        if confirmation:
            if missing_fields(profile):
                raise IncompleteProfile(missing_fields(profile))
            profile = confirm(profile)
            source = "confirmation"
        record.version += 1
        record.updated_at = datetime.now(UTC)
        record.state = state_for(profile)
        values = profile.model_dump()
        values.pop("id")
        values.pop("conversation_id")
        self.session.execute(
            sa.update(BusinessProfileRecord)
            .where(BusinessProfileRecord.id == profile.id)
            .values(**values)
        )
        if content is not None:
            self.session.add(
                MessageRecord(
                    conversation_id=record.id,
                    version=record.version,
                    role=MessageRole.USER,
                    content=content,
                    created_at=record.updated_at,
                )
            )
        self._save_event(record, profile, source)
        self.session.flush()
        return self._view(record)

    def messages(
        self, conversation_id: UUID, token: str, offset: int, limit: int
    ) -> list[MessageView]:
        self._authorise(conversation_id, token)
        records = self.session.scalars(
            sa.select(MessageRecord)
            .where(MessageRecord.conversation_id == conversation_id)
            .order_by(MessageRecord.version, MessageRecord.role)
            .offset(offset)
            .limit(limit)
        )
        return [
            MessageView(**{key: getattr(row, key) for key in MessageView.model_fields})
            for row in records
        ]

    def history(
        self, conversation_id: UUID, token: str, offset: int, limit: int
    ) -> list[RevisionView]:
        self._authorise(conversation_id, token)
        records = self.session.scalars(
            sa.select(ProfileRevisionRecord)
            .where(ProfileRevisionRecord.conversation_id == conversation_id)
            .order_by(ProfileRevisionRecord.version)
            .offset(offset)
            .limit(limit)
        )
        return [
            RevisionView(
                version=row.version,
                source=row.source,
                profile=BusinessProfile.model_validate(row.profile_snapshot),
                created_at=row.created_at,
            )
            for row in records
        ]

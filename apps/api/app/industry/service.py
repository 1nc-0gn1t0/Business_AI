"""One profile extension, same owner/consent/CAS/revisions as v1."""

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.conversation_schemas import ProfilePatch
from app.api.schemas import BusinessProfile
from app.db.models import BusinessProfileRecord, IndustryProfileRecord, MessageRecord
from app.domain.conversation import state_for
from app.domain.enums import DataOrigin, MessageRole
from app.industry.engine import plan
from app.industry.finance import coffee_inputs
from app.industry.registry import (
    FIELDS,
    INDUSTRIES,
    configuration,
    configuration_hash,
    definitions,
    missing,
    reject,
    validate_value,
)
from app.industry.schemas import FieldUpdate, ProfileValue, Scalar, UniversalProfile, UniversalView
from app.leads.consents import require_consent
from app.leads.policy import LeadError
from app.services.conversations import Conversations, IncompleteProfile, VersionConflict


class IndustryProfiles:
    def __init__(self, session: Session):
        self.session = session
        self.conversations = Conversations(session)

    def load(self, owner: UUID, token: str, *, lock: bool = False) -> UniversalProfile:
        view = self.conversations.get(owner, token, lock=lock)
        require_consent(self.session, owner, "assistant")
        row = self.session.get(IndustryProfileRecord, view.profile.id)
        if row:
            profile = UniversalProfile.model_validate(row.document)
            if profile.config_sha256 != configuration_hash(profile.industry):
                profile = profile.model_copy(update={"confirmed_revision": None})
            if profile.revision == view.version:
                return profile
            # A v1 edit or U-03 reply advances the SAME CAS counter. Preserve extensions;
            # conservatively invalidate confirmation and merge only changed common facts.
            profile = profile.model_copy(
                update={"revision": view.version, "confirmed_revision": None}
            )
            old = profile.legacy_snapshot.model_dump(mode="json")
            new = view.profile.model_dump(mode="json")
            updates = []
            for key in ("city", "budget", "funding"):
                if old[key] != new[key]:
                    updates.append(FieldUpdate(field=key, value=new[key]))
            if old["preferences"]["format"] != new["preferences"]["format"]:
                updates.append(FieldUpdate(field="format", value=new["preferences"]["format"]))
            industry = None
            if old["category"] != new["category"]:
                industry = self.legacy_industry(view.profile)
            profile = self.edit(profile, tuple(updates), industry, "legacy_v1")
            return profile.model_copy(update={"legacy_snapshot": view.profile})
        profile = UniversalProfile(
            id=view.profile.id,
            conversation_id=owner,
            revision=view.version,
            industry=self.legacy_industry(view.profile),
            legacy_snapshot=view.profile,
        )
        messages = self.session.scalar(
            sa.select(MessageRecord.content)
            .where(MessageRecord.conversation_id == owner, MessageRecord.role == MessageRole.USER)
            .order_by(MessageRecord.version)
            .limit(1)
        )
        profile = profile.model_copy(
            update={
                "idea": (messages or "")[:1600],
                "raw_industry": view.profile.category,
                "resolution": "known" if profile.industry != "generic" else "unknown",
            }
        )
        updates = [
            FieldUpdate(field=k, value=v)
            for k, v in dict(
                city=view.profile.city,
                budget=str(view.profile.budget) if view.profile.budget is not None else None,
                funding=view.profile.funding,
                format=view.profile.preferences.format,
            ).items()
            if v is not None
        ]
        profile = self.edit(profile, tuple(updates), None, "legacy_v1")
        if view.profile.confirmation_state == "confirmed" and profile.industry == "coffee_shop":
            profile = self.confirm_values(profile)
        return profile

    @staticmethod
    def legacy_industry(profile: BusinessProfile) -> str:
        category = (profile.category or "").casefold()
        return next(
            (c.id for c in INDUSTRIES.values() if category in [a.casefold() for a in c.aliases]),
            "generic",
        )

    @staticmethod
    def edit(
        profile: UniversalProfile,
        updates: tuple[FieldUpdate, ...],
        industry: str | None,
        lineage: str,
        evidence: dict[str, str] | None = None,
    ) -> UniversalProfile:
        current = industry or profile.industry
        configuration(current)
        if len({u.field for u in updates}) != len(updates):
            reject("duplicate_profile_field")
        fields = definitions(current)
        values = dict(profile.values)
        extensions = {k: dict(v) for k, v in profile.extensions.items()}
        extension = extensions.setdefault(current, {})
        for update in updates:
            definition = fields.get(update.field)
            if definition is None:
                reject("unsupported_profile_field")
            target = values if update.field in FIELDS else extension
            if update.value is None:
                target.pop(update.field, None)
                continue
            checked = validate_value(definition, update.value)
            if update.field == "city" and isinstance(checked, str):
                from app.domain.conversation import CITY_FORMS

                checked = CITY_FORMS.get(checked.casefold(), checked)
            previous = target.get(update.field)
            if previous and previous.value == checked:
                continue
            target[update.field] = ProfileValue.model_validate(
                dict(
                    value=checked,
                    unit=definition.unit,
                    origin=DataOrigin.USER_INPUT,
                    epistemic="user_provided",
                    review="proposed",
                    evidence=(evidence or {}).get(update.field, str(update.value))[:500],
                    lineage=lineage,
                )
            )
        return profile.model_copy(
            update={
                "industry": current,
                "config_version": configuration(current).version,
                "config_sha256": configuration_hash(current),
                "configuration_snapshot": configuration(current),
                "values": values,
                "extensions": extensions,
                "confirmed_revision": None,
                "deferred_fields": tuple(
                    k for k in profile.deferred_fields if k not in {u.field for u in updates}
                )
                if current == profile.industry
                else (),
            }
        )

    @staticmethod
    def confirm_values(profile: UniversalProfile) -> UniversalProfile:
        return profile.model_copy(
            update={
                "confirmed_revision": profile.revision,
                "values": {
                    k: v.model_copy(update={"review": "confirmed"})
                    for k, v in profile.values.items()
                },
                "extensions": {
                    k: {f: v.model_copy(update={"review": "confirmed"}) for f, v in values.items()}
                    for k, values in profile.extensions.items()
                },
            }
        )

    def view(self, owner: UUID, token: str, extraction: str = "none") -> UniversalView:
        profile = self.load(owner, token)
        return UniversalView.model_validate(
            dict(
                conversation=self.conversations.get(owner, token),
                profile=profile,
                configuration=configuration(profile.industry),
                field_definitions=tuple(definitions(profile.industry).values()),
                plan=plan(self.session, profile),
                coffee_inputs=coffee_inputs(profile),
                extraction=extraction,
            )
        )

    def save(
        self,
        owner: UUID,
        token: str,
        version: int,
        profile: UniversalProfile,
        *,
        content: str | None = None,
        confirmation: bool = False,
        consent_revision: int | None = None,
        answer: str | None = None,
        extraction: str = "none",
    ) -> UniversalView:
        record = self.conversations._authorise(owner, token, lock=True)
        consent = require_consent(self.session, owner, "assistant")
        if record.version != version:
            raise VersionConflict(record.version)
        if consent_revision is not None and consent.revision != consent_revision:
            raise LeadError("consent_revision_conflict")
        incomplete = tuple(k for k in missing(profile) if k not in profile.deferred_fields)
        if confirmation and incomplete:
            raise IncompleteProfile(incomplete)
        if confirmation and profile.resolution == "ambiguous":
            raise IncompleteProfile(("industry",))
        if confirmation and profile.config_sha256 != configuration_hash(profile.industry):
            reject("industry_config_changed")

        # A common-field projection is NOT a lossless v2→v1 conversion. The original
        # v1 snapshot/preferences and all extensions remain stored in the v2 document.
        def get(k: str) -> Scalar | None:
            return profile.values[k].value if k in profile.values else None

        patch = ProfilePatch.model_validate(
            dict(
                city=get("city"),
                category=configuration(profile.industry).label
                if profile.industry != "generic"
                else profile.raw_industry or "Неизвестный бизнес",
                budget=get("budget"),
                funding=get("funding"),
                preferences={"format": get("format")},
            )
        )
        legacy = self.conversations.update(
            owner,
            token,
            version,
            patch=patch,
            mode="ollama" if extraction == "ollama" else None,
        )
        if content is not None and extraction == "clarification_fallback":
            record.extraction_mode = "rules"
        # Every v2 edit invalidates v1 confirmation, including extension-only changes.
        self.session.execute(
            sa.update(BusinessProfileRecord)
            .where(BusinessProfileRecord.conversation_id == owner)
            .values(confirmation_state="draft")
        )
        self.session.flush()
        if confirmation and profile.industry == "coffee_shop" and not missing(profile):
            from app.domain.conversation import confirm

            confirm(self.conversations._profile(owner))
            self.session.execute(
                sa.update(BusinessProfileRecord)
                .where(BusinessProfileRecord.conversation_id == owner)
                .values(confirmation_state="confirmed")
            )
        from app.db.models import ProfileRevisionRecord

        current_legacy = self.conversations._profile(owner)
        record.state = state_for(current_legacy)
        self.session.execute(
            sa.update(ProfileRevisionRecord)
            .where(
                ProfileRevisionRecord.conversation_id == owner,
                ProfileRevisionRecord.version == legacy.version,
            )
            .values(profile_snapshot=current_legacy.model_dump(mode="json"))
        )
        profile = profile.model_copy(
            update={
                "revision": legacy.version,
                "legacy_snapshot": self.conversations._profile(owner),
            }
        )
        if confirmation:
            profile = self.confirm_values(profile)
        if len(profile.model_dump_json().encode()) > 49152:
            reject("profile_too_large")
        if content is not None:
            from app.limits.storage import check_growth

            check_growth(self.session, owner, {"messages": 1})
            self.session.add(
                MessageRecord(
                    conversation_id=owner,
                    version=legacy.version,
                    role=MessageRole.USER,
                    content=content,
                    created_at=datetime.now(UTC),
                )
            )
        question = plan(self.session, profile).next_question
        message = (
            answer
            or question
            or (
                "Параметры подтверждены. Можно продолжить доступный анализ."
                if confirmation
                else "Проверьте параметры проекта. Всё верно?"
            )
        )
        self.session.execute(
            sa.update(MessageRecord)
            .where(
                MessageRecord.conversation_id == owner,
                MessageRecord.version == legacy.version,
                MessageRecord.role == MessageRole.ASSISTANT,
            )
            .values(content=message)
        )
        row = self.session.get(IndustryProfileRecord, profile.id)
        if row is None:
            self.session.add(
                IndustryProfileRecord(
                    profile_id=profile.id, document=profile.model_dump(mode="json")
                )
            )
        else:
            row.document = profile.model_dump(mode="json")
        self.session.flush()
        return self.view(owner, token, extraction)

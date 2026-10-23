from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.conversation_schemas import ConversationView
from app.bank.matching import catalogue_view, digest, load_catalogue, today
from app.bank.schemas import CatalogueView
from app.db.models import AuditEventRecord, ConsentRecord, LeadDraftRecord, LeadSubmissionRecord
from app.domain.enums import ConfirmationState
from app.leads.consents import latest_consent, require_consent
from app.leads.policy import TEXTS, LeadError, MockLeadAdapter, check_action, fingerprint
from app.leads.schemas import (
    AuditView,
    ConsentDecision,
    ConsentState,
    ConsentView,
    DraftAction,
    DraftEdit,
    DraftInput,
    LeadDraft,
    LeadPayload,
    LeadReceipt,
    LeadWorkspace,
    Purpose,
    SubmitRequest,
)
from app.services.conversations import Conversations


class LeadAdapter(Protocol):
    def submit(self, draft: LeadDraft, **values: object) -> LeadReceipt: ...


def current_catalogue() -> CatalogueView:
    try:
        return catalogue_view(load_catalogue(), today())
    except (OSError, ValueError):
        raise LeadError("bank_catalogue_unavailable", 503) from None


class Leads:
    def __init__(self, session: Session, adapter: LeadAdapter | None = None):
        self.session = session
        self.adapter = adapter or MockLeadAdapter()

    def authorise(self, conversation_id: UUID, token: str) -> ConversationView:
        # Same lock as profile writes: consent revocation, profile changes and submission
        # serialize in a single transaction. No model inference or HTTP while locked.
        return Conversations(self.session).get(conversation_id, token, lock=True)

    def audit(self, conversation_id: UUID, action: str, object_id: UUID) -> None:
        self.session.add(
            AuditEventRecord(
                conversation_id=conversation_id,
                action=action,
                object_id=object_id,
                created_at=datetime.now(UTC),
            )
        )

    def consents(self, conversation_id: UUID) -> ConsentState:
        return ConsentState(
            texts=TEXTS,
            consents=tuple(latest_consent(self.session, conversation_id, t.purpose) for t in TEXTS),
        )

    def decide(
        self, conversation_id: UUID, purpose: Purpose, body: ConsentDecision
    ) -> ConsentState:
        current = latest_consent(self.session, conversation_id, purpose)
        text = next(t for t in TEXTS if t.purpose == purpose)
        if body.expected_revision != current.revision:
            raise LeadError("consent_revision_conflict")
        if body.text_version != text.version:
            raise LeadError("consent_text_changed")
        now = datetime.now(UTC)
        status = {"grant": "granted", "decline": "declined", "withdraw": "withdrawn"}[body.decision]
        if current.status == status and current.text_version == text.version:
            return self.consents(conversation_id)
        if body.decision == "withdraw" and current.status != "granted":
            raise LeadError("consent_not_granted")
        view = ConsentView.model_validate(
            {
                "id": uuid4(),
                "purpose": purpose,
                "revision": current.revision + 1,
                "text_version": text.version,
                "text_snapshot": text,
                "status": status,
                "recorded_at": now,
                "given_at": now if body.decision == "grant" else current.given_at,
                "withdrawn_at": now if body.decision == "withdraw" else None,
            }
        )
        self.session.add(
            ConsentRecord(
                id=view.id,
                conversation_id=conversation_id,
                purpose=purpose,
                revision=view.revision,
                document=view.model_dump(mode="json"),
            )
        )
        self.audit(conversation_id, "consent_" + body.decision, view.id or conversation_id)
        self.session.flush()
        return self.consents(conversation_id)

    def draft(self, view: ConversationView, draft_id: UUID) -> tuple[LeadDraftRecord, LeadDraft]:
        row = self.session.scalar(
            sa.select(LeadDraftRecord).where(
                LeadDraftRecord.id == draft_id,
                LeadDraftRecord.conversation_id == view.id,
            )
        )
        if row is None:
            raise LeadError("lead_not_found", 404)
        draft = LeadDraft.model_validate(row.document)
        return row, draft.model_copy(
            update={
                "stale": (
                    draft.profile_version != view.version
                    or view.profile.confirmation_state != ConfirmationState.CONFIRMED
                )
            }
        )

    def workspace(self, view: ConversationView) -> LeadWorkspace:
        rows = self.session.scalars(
            sa.select(LeadDraftRecord)
            .where(
                LeadDraftRecord.conversation_id == view.id,
            )
            .order_by(LeadDraftRecord.id)
        )
        drafts = tuple(self.draft(view, row.id)[1] for row in rows)
        receipts = tuple(
            LeadReceipt.model_validate(row.document)
            for row in self.session.scalars(
                sa.select(LeadSubmissionRecord)
                .where(LeadSubmissionRecord.conversation_id == view.id)
                .order_by(LeadSubmissionRecord.id)
            )
        )
        return LeadWorkspace(drafts=drafts, receipts=receipts)

    def payload(self, view: ConversationView, body: DraftInput) -> LeadPayload:
        require_consent(self.session, view.id, "assistant")
        require_consent(self.session, view.id, "demo_lead")
        if (
            view.version != body.expected_profile_version
            or view.profile.confirmation_state != ConfirmationState.CONFIRMED
        ):
            raise LeadError("lead_profile_stale")
        catalogue = current_catalogue()
        if catalogue.fingerprint != body.catalogue_fingerprint:
            raise LeadError("bank_catalogue_version_conflict")
        entries = {p.product.id: p for p in catalogue.products if p.availability != "blocked"}
        if not set(body.product_ids) <= entries.keys():
            raise LeadError("lead_product_unavailable")
        source = {
            "city": view.profile.city,
            "category": view.profile.category,
            "budget": view.profile.budget,
            "funding": view.profile.funding,
            "format": view.profile.preferences.format,
        }
        return LeadPayload(
            fields=body.fields,
            products=tuple(entries[key] for key in sorted(body.product_ids)),
            catalogue_version=catalogue.version,
            catalogue_fingerprint=catalogue.fingerprint,
            field_origins={
                key: "confirmed_profile"
                if getattr(body.fields, key) == source[key]
                else "draft_user_input"
                for key in source
                if getattr(body.fields, key) is not None
            },
        )

    def prepare(
        self, view: ConversationView, body: DraftInput, draft_id: UUID | None = None
    ) -> LeadDraft:
        row = None
        previous = None
        if draft_id:
            row, previous = self.draft(view, draft_id)
            if previous.state == "submitted":
                raise LeadError("lead_already_submitted")
            if not isinstance(body, DraftEdit) or previous.revision != body.expected_revision:
                raise LeadError("lead_revision_conflict")
        payload = self.payload(view, body)
        now = datetime.now(UTC)
        result = LeadDraft(
            id=draft_id or uuid4(),
            revision=previous.revision + 1 if previous else 1,
            profile_version=view.version,
            profile_snapshot=view.profile,
            consents=(
                require_consent(self.session, view.id, "assistant"),
                require_consent(self.session, view.id, "demo_lead"),
            ),
            payload=payload,
            payload_fingerprint=fingerprint(payload, view.version),
            state="draft",
            created_at=previous.created_at if previous else now,
            updated_at=now,
        )
        if row:
            row.document = result.model_dump(mode="json")
        else:
            row = LeadDraftRecord(
                id=result.id, conversation_id=view.id, document=result.model_dump(mode="json")
            )
            self.session.add(row)
        self.audit(view.id, "draft_updated" if previous else "draft_created", result.id)
        self.session.flush()
        return result

    def validate(
        self, view: ConversationView, draft: LeadDraft, body: DraftAction
    ) -> tuple[ConsentView, ...]:
        consents = (
            require_consent(self.session, view.id, "assistant"),
            require_consent(self.session, view.id, "demo_lead"),
        )
        check_action(draft, body)
        if consents != draft.consents:
            raise LeadError("lead_consent_changed")
        catalogue = current_catalogue()
        if catalogue.fingerprint != draft.payload.catalogue_fingerprint:
            raise LeadError("bank_catalogue_version_conflict")
        entries = {p.product.id for p in catalogue.products if p.availability != "blocked"}
        if not {p.product.id for p in draft.payload.products} <= entries:
            raise LeadError("lead_product_unavailable")
        return consents

    def confirm(self, view: ConversationView, draft_id: UUID, body: DraftAction) -> LeadDraft:
        row, draft = self.draft(view, draft_id)
        self.validate(view, draft, body)
        if draft.state == "submitted":
            raise LeadError("lead_already_submitted")
        if draft.state == "confirmed":
            return draft
        now = datetime.now(UTC)
        result = draft.model_copy(
            update={"state": "confirmed", "confirmed_at": now, "updated_at": now}
        )
        row.document = result.model_dump(mode="json")
        self.audit(view.id, "draft_confirmed", draft.id)
        self.session.flush()
        return result

    def submit(self, view: ConversationView, draft_id: UUID, body: SubmitRequest) -> LeadReceipt:
        row, draft = self.draft(view, draft_id)
        consents = self.validate(view, draft, body)
        request_hash = digest({"draft_id": str(draft_id), **body.model_dump(mode="json")})
        replay = self.session.scalar(
            sa.select(LeadSubmissionRecord).where(
                LeadSubmissionRecord.conversation_id == view.id,
                sa.or_(
                    LeadSubmissionRecord.idempotency_key == body.idempotency_key,
                    LeadSubmissionRecord.draft_id == draft_id,
                ),
            )
        )
        if replay:
            if replay.request_fingerprint != request_hash:
                raise LeadError("lead_idempotency_conflict")
            return LeadReceipt.model_validate(replay.document)
        if draft.state != "confirmed" or draft.confirmed_at is None:
            raise LeadError("lead_confirmation_required")
        receipt = self.adapter.submit(draft, consents=consents, created_at=datetime.now(UTC))
        self.session.add(
            LeadSubmissionRecord(
                id=receipt.id,
                conversation_id=view.id,
                draft_id=draft.id,
                idempotency_key=body.idempotency_key,
                request_fingerprint=request_hash,
                document=receipt.model_dump(mode="json"),
            )
        )
        row.document = draft.model_copy(
            update={"state": "submitted", "updated_at": receipt.created_at}
        ).model_dump(mode="json")
        self.audit(view.id, "demo_submission_created", receipt.id)
        self.session.flush()
        return receipt

    def events(self, conversation_id: UUID, offset: int, limit: int) -> list[AuditView]:
        return [
            AuditView(
                id=row.id, action=row.action, object_id=row.object_id, created_at=row.created_at
            )
            for row in self.session.scalars(
                sa.select(AuditEventRecord)
                .where(
                    AuditEventRecord.conversation_id == conversation_id,
                )
                .order_by(AuditEventRecord.created_at, AuditEventRecord.id)
                .offset(offset)
                .limit(limit)
            )
        ]

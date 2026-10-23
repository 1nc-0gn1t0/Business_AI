from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import ConsentRecord
from app.leads.policy import TEXTS, LeadError
from app.leads.schemas import ConsentView, Purpose


def latest_consent(session: Session, conversation_id: UUID, purpose: Purpose) -> ConsentView:
    row = session.scalar(
        sa.select(ConsentRecord)
        .where(ConsentRecord.conversation_id == conversation_id, ConsentRecord.purpose == purpose)
        .order_by(ConsentRecord.revision.desc())
        .limit(1)
    )
    return (
        ConsentView.model_validate(row.document)
        if row
        else ConsentView(
            purpose=purpose,
            text_version=next(t.version for t in TEXTS if t.purpose == purpose),
        )
    )


def require_consent(session: Session, conversation_id: UUID, purpose: Purpose) -> ConsentView:
    consent = latest_consent(session, conversation_id, purpose)
    text = next(t for t in TEXTS if t.purpose == purpose)
    if consent.status != "granted" or consent.text_version != text.version:
        raise LeadError(f"consent_required_{purpose}", 403)
    return consent

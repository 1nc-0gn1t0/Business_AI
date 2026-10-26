from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEventRecord,
    ConsentRecord,
    ConversationRecord,
    LeadDraftRecord,
    LeadSubmissionRecord,
    MessageRecord,
    ProfileRevisionRecord,
    ReportRecord,
)
from app.limits.config import Resource, policy

TABLES = {
    "conversations": ConversationRecord.__table__,
    "messages": MessageRecord.__table__,
    "revisions": ProfileRevisionRecord.__table__,
    "consents": ConsentRecord.__table__,
    "drafts": LeadDraftRecord.__table__,
    "receipts": LeadSubmissionRecord.__table__,
    "audit": AuditEventRecord.__table__,
    "reports": ReportRecord.__table__,
}


def refused(resource: str, scope: str, limit: int) -> None:
    code = (
        "report_limit_reached"
        if resource == "reports" and scope == "conversation"
        else "resource_quota_exceeded"
    )
    # Stock quotas have no known reset time: never invent Retry-After.
    raise HTTPException(
        429, detail={"code": code, "resource": resource, "scope": scope, "limit": limit}
    )


def check_growth(
    session: Session,
    owner: UUID | None,
    additions: dict[Resource, int],
    *,
    lock: bool = True,
    report_document: dict[str, object] | None = None,
    pdf: bytes = b"",
    deactivation: bool = False,
) -> None:
    # Only a transition from granted -> withdrawn/declined may bypass stock caps.
    # Once caps are full grants are blocked, so at most 3 deactivations/owner remain.
    if deactivation:
        return
    cfg = policy()
    if lock:
        session.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended('business-ai-h02-storage',0))")
        )
    with session.no_autoflush:
        for name, growth in additions.items():
            table = TABLES[name]
            total = session.scalar(sa.select(sa.func.count()).select_from(table)) or 0
            if total + growth > cfg.global_records[name]:
                refused(name, "deployment", cfg.global_records[name])
            if owner is not None and name in cfg.owner_records:
                count = (
                    session.scalar(
                        sa.select(sa.func.count())
                        .select_from(table)
                        .where(table.c.conversation_id == owner)
                    )
                    or 0
                )
                if count + growth > cfg.owner_records[name]:
                    refused(name, "conversation", cfg.owner_records[name])
        if "reports" in additions:
            byte_size = sa.func.octet_length(ReportRecord.pdf) + sa.func.octet_length(
                sa.cast(ReportRecord.snapshot, sa.Text)
            )
            current = session.scalar(sa.select(sa.func.coalesce(sa.func.sum(byte_size), 0))) or 0
            incoming = (
                0
                if report_document is None
                else (
                    session.scalar(
                        sa.select(
                            sa.func.octet_length(
                                sa.cast(sa.literal(report_document, type_=JSONB), sa.Text)
                            )
                        )
                    )
                    or 0
                )
            )
            if (
                current >= cfg.report_storage_bytes
                or current + incoming + len(pdf) > cfg.report_storage_bytes
            ):
                refused("report_bytes", "deployment", cfg.report_storage_bytes)

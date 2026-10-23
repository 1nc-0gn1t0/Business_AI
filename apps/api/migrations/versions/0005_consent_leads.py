"""Append-only consent decisions, local mock leads and audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_consent_leads"
down_revision = "0004_osm_geo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("document", JSONB(), nullable=False),
        sa.UniqueConstraint("conversation_id", "purpose", "revision"),
        sa.CheckConstraint("revision > 0", name="ck_consent_revision"),
        sa.CheckConstraint(
            "purpose IN ('assistant', 'marketing', 'demo_lead')", name="ck_consent_purpose"
        ),
        sa.CheckConstraint("jsonb_typeof(document) = 'object'", name="ck_consent_document"),
    )
    op.create_table(
        "lead_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("document", JSONB(), nullable=False),
        sa.CheckConstraint("jsonb_typeof(document) = 'object'", name="ck_draft_document"),
    )
    op.create_table(
        "lead_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column(
            "draft_id", sa.Uuid(), sa.ForeignKey("lead_drafts.id"), nullable=False, unique=True
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("document", JSONB(), nullable=False),
        sa.UniqueConstraint("conversation_id", "idempotency_key"),
        sa.CheckConstraint("jsonb_typeof(document) = 'object'", name="ck_submission_document"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("consents", "lead_drafts", "lead_submissions", "audit_events"):
        op.create_index(f"ix_{table}_conversation_id", table, ["conversation_id"])


def downgrade() -> None:
    for table in ("audit_events", "lead_submissions", "lead_drafts", "consents"):
        op.drop_table(table)

"""Immutable report snapshots and generated PDF, owned by a guest conversation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0008_analytical_reports"
down_revision = "0007_data_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytical_reports",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("conversation_id", UUID(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("snapshot_sha256", sa.Text(), nullable=False),
        sa.Column("pdf", sa.LargeBinary(), nullable=False),
        sa.Column("pdf_sha256", sa.Text(), nullable=False),
        sa.CheckConstraint("snapshot_sha256 ~ '^[0-9a-f]{64}$'", name="ck_report_snapshot_sha"),
        sa.CheckConstraint("pdf_sha256 ~ '^[0-9a-f]{64}$'", name="ck_report_pdf_sha"),
        sa.CheckConstraint("octet_length(pdf) <= 3145728", name="ck_report_pdf_size"),
    )
    op.create_index(
        "ix_analytical_reports_conversation_id", "analytical_reports", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_table("analytical_reports")

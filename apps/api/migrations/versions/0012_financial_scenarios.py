"""Owner-scoped financial inputs, bounded action history and immutable v2 snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012_financial_scenarios"
down_revision = "0011_industry_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_workspaces",
        sa.Column(
            "conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), primary_key=True
        ),
        sa.Column("document", JSONB(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(document) = 'object' AND octet_length(document::text) <= 65536",
            name="ck_financial_workspace_size",
        ),
    )
    op.create_table(
        "financial_actions",
        sa.Column(
            "conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), primary_key=True
        ),
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.CheckConstraint(
            "octet_length(snapshot::text) <= 65536", name="ck_financial_action_size"
        ),
    )
    op.create_index(
        "ix_financial_action_owner_created", "financial_actions", ["conversation_id", "created_at"]
    )
    op.create_table(
        "financial_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.UniqueConstraint("conversation_id", "fingerprint"),
        sa.CheckConstraint(
            "octet_length(snapshot::text) <= 196608", name="ck_financial_result_size"
        ),
    )
    op.create_index(
        "ix_financial_result_owner_created", "financial_results", ["conversation_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("financial_results")
    op.drop_table("financial_actions")
    op.drop_table("financial_workspaces")

"""Bounded owner-scoped agent traces, independent of v1 profiles/reports."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_agent_runs"
down_revision = "0009_acquisition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("consent_revision", sa.Integer(), nullable=False),
        sa.Column("operator", sa.Boolean(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("job_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("octet_length(response::text) <= 98304", name="ck_agent_response_size"),
    )
    op.create_index("ix_agent_owner_created", "agent_runs", ["conversation_id", "created_at"])
    op.create_index(
        "ix_agent_owner_active",
        "agent_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("state = 'running'"),
    )


def downgrade() -> None:
    op.drop_table("agent_runs")

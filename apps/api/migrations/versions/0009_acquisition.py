"""Bounded operator acquisition jobs, requests and durable event cursors."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0009_acquisition"
down_revision = "0008_analytical_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "acquisition_jobs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("expected_version", sa.Text()),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("fencing_token", sa.Integer(), nullable=False),
        sa.Column("event_cursor", sa.Integer(), nullable=False),
        sa.Column("installation", sa.Text()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("artifact", sa.LargeBinary()),
        sa.Column("checkpoint", JSONB(), nullable=False),
        sa.Column("result", JSONB()),
        sa.Column("error_code", sa.Text()),
        sa.CheckConstraint(
            "attempt BETWEEN 0 AND 2 AND fencing_token >= 0 AND event_cursor >= 0",
            name="ck_acquisition_counters",
        ),
        sa.CheckConstraint(
            "artifact IS NULL OR octet_length(artifact) <= 8388608", name="ck_acquisition_artifact"
        ),
        sa.CheckConstraint(
            "state IN ('queued','claimed','fetching','validating','importing','verifying',"
            "'activating','retry_wait','cancel_requested','cancelled','failed',"
            "'recovery_required','succeeded')",
            name="ck_acquisition_state",
        ),
    )
    op.create_index("ix_acquisition_pending", "acquisition_jobs", ["state", "next_attempt_at"])
    op.create_index(
        "ix_acquisition_active_scope",
        "acquisition_jobs",
        ["scope_hash"],
        unique=True,
        postgresql_where=sa.text("state NOT IN ('succeeded','failed','cancelled')"),
    )
    op.create_table(
        "acquisition_requests",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("job_id", UUID(), sa.ForeignKey("acquisition_jobs.id"), nullable=False),
    )
    op.create_table(
        "acquisition_events",
        sa.Column("job_id", UUID(), sa.ForeignKey("acquisition_jobs.id"), primary_key=True),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("message_code", sa.Text(), nullable=False),
    )
    op.create_index("ix_acquisition_events_timestamp", "acquisition_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("acquisition_events")
    op.drop_table("acquisition_requests")
    op.drop_table("acquisition_jobs")

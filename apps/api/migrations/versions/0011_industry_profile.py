"""Bounded one-to-one v2 extension of the existing owner-bound business profile."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_industry_profile"
down_revision = "0010_agent_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "industry_profiles",
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("business_profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("document", JSONB(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(document) = 'object' AND octet_length(document::text) <= 49152",
            name="ck_industry_profile_size",
        ),
    )


def downgrade() -> None:
    op.drop_table("industry_profiles")

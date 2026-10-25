"""Versioned local provider datasets; OSM tables remain authoritative."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_data_providers"
down_revision = "0006_walking_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_datasets",
        sa.Column("provider", sa.Text(), primary_key=True),
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("data_version", sa.Text(), primary_key=True),
        sa.Column("revision", sa.Text(), nullable=False),
        sa.Column("document", JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "slug", "revision"),
        sa.CheckConstraint("provider = 'synthetic'", name="ck_provider_implemented_import"),
        sa.CheckConstraint("data_version ~ '^[0-9a-f]{64}$'", name="ck_provider_version"),
        sa.CheckConstraint("document->>'origin' = 'synthetic'", name="ck_provider_origin"),
    )
    op.create_index(
        "ix_provider_active",
        "provider_datasets",
        ["provider", "slug"],
        unique=True,
        postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    op.drop_table("provider_datasets")

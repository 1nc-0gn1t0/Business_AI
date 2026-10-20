"""Initial business profiles, analysis snapshots and metrics with provenance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_contracts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "business_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("budget", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "funding",
            sa.Enum("own_funds", "loan", "mixed", "undecided", name="funding"),
            nullable=True,
        ),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
        sa.Column(
            "confirmation_state",
            sa.Enum("draft", "confirmed", name="confirmation_state"),
            server_default="draft",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
        sa.CheckConstraint("budget >= 0 AND budget <> 'NaN'::numeric", name="ck_profile_budget"),
        sa.CheckConstraint("city IS NULL OR length(btrim(city)) > 0", name="ck_profile_city"),
        sa.CheckConstraint(
            "category IS NULL OR length(btrim(category)) > 0", name="ck_profile_category"
        ),
        sa.CheckConstraint("jsonb_typeof(preferences) = 'object'", name="ck_profile_preferences"),
    )
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("dataset_versions", postgresql.JSONB(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("tool_trace_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("jsonb_typeof(profile_snapshot) = 'object'", name="ck_run_snapshot"),
        sa.CheckConstraint(
            "jsonb_typeof(dataset_versions) = 'object' AND dataset_versions <> '{}'::jsonb",
            name="ck_run_datasets",
        ),
        sa.CheckConstraint("length(btrim(algorithm_version)) > 0", name="ck_run_algorithm"),
    )
    op.create_table(
        "location_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column(
            "origin",
            sa.Enum(
                "open_data",
                "licensed",
                "modelled",
                "synthetic",
                "user_input",
                "bank_internal",
                name="data_origin",
            ),
            nullable=False,
        ),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_version", sa.Text(), nullable=False),
        sa.Column(
            "confidence",
            sa.Enum("low", "medium", "high", "not_applicable", name="confidence"),
            nullable=False,
        ),
        sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint("length(btrim(metric)) > 0", name="ck_metric_name"),
        sa.CheckConstraint("length(btrim(unit)) > 0", name="ck_metric_unit"),
        sa.CheckConstraint("length(btrim(source_name)) > 0", name="ck_metric_source"),
        sa.CheckConstraint("length(btrim(data_version)) > 0", name="ck_metric_version"),
        sa.CheckConstraint(
            "value > '-Infinity'::double precision AND value < 'Infinity'::double precision",
            name="ck_metric_finite",
        ),
        sa.CheckConstraint(
            "observed_at IS NULL OR observed_at <= generated_at", name="ck_metric_dates"
        ),
        sa.CheckConstraint("jsonb_typeof(limitations) = 'array'", name="ck_metric_limitations"),
        sa.CheckConstraint(
            "origin <> 'synthetic' OR "
            "(confidence = 'not_applicable' AND jsonb_array_length(limitations) > 0)",
            name="ck_metric_synthetic",
        ),
    )
    op.create_index("ix_location_metrics_analysis_run_id", "location_metrics", ["analysis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_location_metrics_analysis_run_id", table_name="location_metrics")
    op.drop_table("location_metrics")
    op.drop_table("analysis_runs")
    op.drop_table("business_profiles")
    for name in ("confidence", "data_origin", "confirmation_state", "funding"):
        postgresql.ENUM(name=name).drop(op.get_bind())
    # The extension may predate this revision and is shared infrastructure. Keep it.

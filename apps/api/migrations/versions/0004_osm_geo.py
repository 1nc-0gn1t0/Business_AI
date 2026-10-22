"""Versioned OSM snapshots, POI and complete administrative boundaries."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.db.spatial import Geometry

revision = "0004_osm_geo"
down_revision = "0003_llm_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_datasets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("bbox", JSONB(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("data_version", sa.String(64), nullable=False),
        sa.Column("osm_base", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("poi_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("district_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("diagnostics", JSONB(), nullable=False),
        sa.UniqueConstraint("slug", "data_version"),
        sa.CheckConstraint("data_version ~ '^[0-9a-f]{64}$'", name="ck_geo_version"),
        sa.CheckConstraint("osm_base <= fetched_at", name="ck_geo_dates"),
        sa.CheckConstraint("poi_count >= 0 AND district_count >= 0", name="ck_geo_counts"),
    )
    op.create_index(
        "ix_geo_active_slug",
        "geo_datasets",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "geo_pois",
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("geo_datasets.id"), primary_key=True),
        sa.Column("osm_type", sa.Text(), primary_key=True),
        sa.Column("osm_id", sa.BigInteger(), primary_key=True),
        sa.Column("osm_version", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("categories", ARRAY(sa.Text()), nullable=False),
        sa.Column("tags", JSONB(), nullable=False),
        sa.Column("representation", sa.Text(), nullable=False),
        sa.Column("geom", Geometry(), nullable=False),
        sa.CheckConstraint("osm_type IN ('node', 'way', 'relation')", name="ck_poi_osm_type"),
        sa.CheckConstraint("osm_id > 0 AND osm_version > 0", name="ck_poi_identity"),
        sa.CheckConstraint("cardinality(categories) > 0", name="ck_poi_categories"),
    )
    op.create_index("ix_geo_poi_geom", "geo_pois", ["geom"], postgresql_using="gist")
    op.create_index(
        "ix_geo_poi_geography", "geo_pois", [sa.text("(geom::geography)")], postgresql_using="gist"
    )
    op.create_index("ix_geo_poi_categories", "geo_pois", ["categories"], postgresql_using="gin")
    op.create_table(
        "geo_districts",
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("geo_datasets.id"), primary_key=True),
        sa.Column("osm_id", sa.BigInteger(), primary_key=True),
        sa.Column("osm_version", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("admin_level", sa.Integer(), nullable=False),
        sa.Column("geom", Geometry("MULTIPOLYGON"), nullable=False),
        sa.CheckConstraint("osm_id > 0 AND osm_version > 0", name="ck_district_identity"),
        sa.CheckConstraint("ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_district_geom"),
    )
    op.create_index("ix_geo_district_geom", "geo_districts", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("geo_districts")
    op.drop_table("geo_pois")
    op.drop_table("geo_datasets")

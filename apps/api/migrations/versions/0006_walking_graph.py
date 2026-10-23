"""Immutable walking graph snapshots and OSM-node-connected directed edges."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.db.spatial import Geometry

revision = "0006_walking_graph"
down_revision = "0005_consent_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "walk_graphs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("graph_version", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("document", JSONB(), nullable=False),
        sa.UniqueConstraint("slug", "graph_version"),
    )
    op.create_index(
        "ix_walk_active_slug",
        "walk_graphs",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "walk_edges",
        sa.Column("graph_id", sa.Uuid(), sa.ForeignKey("walk_graphs.id"), primary_key=True),
        sa.Column("edge_id", sa.Integer(), primary_key=True),
        sa.Column("way_id", sa.BigInteger(), nullable=False),
        sa.Column("u", sa.BigInteger(), nullable=False),
        sa.Column("v", sa.BigInteger(), nullable=False),
        sa.Column("forward", sa.Boolean(), nullable=False),
        sa.Column("backward", sa.Boolean(), nullable=False),
        sa.Column("length_m", sa.Double(), nullable=False),
        sa.Column("geom", Geometry("LINESTRING"), nullable=False),
        sa.Column("tags", JSONB(), nullable=False),
        sa.CheckConstraint("length_m > 0 AND length_m < 100000", name="ck_walk_length"),
        sa.CheckConstraint("forward OR backward", name="ck_walk_direction"),
    )
    op.create_index("ix_walk_geom", "walk_edges", ["geom"], postgresql_using="gist")
    op.create_index(
        "ix_walk_geography", "walk_edges", [sa.text("(geom::geography)")], postgresql_using="gist"
    )


def downgrade() -> None:
    op.drop_table("walk_edges")
    op.drop_table("walk_graphs")

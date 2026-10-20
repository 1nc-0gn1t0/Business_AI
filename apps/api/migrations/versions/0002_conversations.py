"""Persist guest conversations, messages and versioned profile history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_conversations"
down_revision = "0001_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "state",
            sa.Enum("collecting", "awaiting_confirmation", "confirmed", name="conversation_state"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("version >= 0", name="ck_conversation_version"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_conversation_token_hash"),
    )
    # Preserve pre-BA-004 profiles; no valid bearer secret exists for imported rows.
    op.execute("""
        INSERT INTO conversations (id, token_hash, state, version, created_at, updated_at)
        SELECT conversation_id, repeat('0', 64), 'collecting', 0, now(), now()
        FROM business_profiles
    """)
    op.create_foreign_key(
        "fk_profile_conversation",
        "business_profiles",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("role", sa.Enum("user", "assistant", name="message_role"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("conversation_id", "version", "role"),
        sa.CheckConstraint("version >= 0", name="ck_message_version"),
        sa.CheckConstraint("length(btrim(content)) BETWEEN 1 AND 4000", name="ck_message_content"),
    )
    op.create_table(
        "profile_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("conversation_id", "version"),
        sa.CheckConstraint("version >= 0", name="ck_revision_version"),
        sa.CheckConstraint(
            "jsonb_typeof(profile_snapshot) = 'object'", name="ck_revision_snapshot"
        ),
        sa.CheckConstraint(
            "source IN ('created', 'message', 'patch', 'confirmation', 'legacy_import')",
            name="ck_revision_source",
        ),
    )
    op.execute("""
        INSERT INTO profile_revisions
            (id, conversation_id, version, source, profile_snapshot, created_at)
        SELECT gen_random_uuid(), conversation_id, 0, 'legacy_import', jsonb_build_object(
            'id', id, 'conversation_id', conversation_id, 'city', city, 'category', category,
            'budget', budget::text, 'funding', funding, 'preferences', preferences,
            'confirmation_state', confirmation_state
        ), now() FROM business_profiles
    """)


def downgrade() -> None:
    op.drop_table("profile_revisions")
    op.drop_table("messages")
    op.drop_constraint("fk_profile_conversation", "business_profiles", type_="foreignkey")
    op.drop_table("conversations")
    for name in ("message_role", "conversation_state"):
        postgresql.ENUM(name=name).drop(op.get_bind())

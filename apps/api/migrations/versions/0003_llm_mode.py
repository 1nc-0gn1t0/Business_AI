"""Remember the extraction provider without changing existing conversation contracts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_llm_mode"
down_revision = "0002_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("extraction_mode", sa.Text(), server_default="rules", nullable=False),
    )
    op.create_check_constraint(
        "ck_conversation_mode", "conversations", "extraction_mode IN ('rules', 'stub', 'ollama')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_conversation_mode", "conversations", type_="check")
    op.drop_column("conversations", "extraction_mode")

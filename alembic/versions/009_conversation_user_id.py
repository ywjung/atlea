"""Add user_id to conversations for IDOR protection

Revision ID: 009
Revises: 008
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("user_id", sa.String(100), nullable=True),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_column("conversations", "user_id")

"""Conversation and persona tables

Revision ID: 004
Revises: 003
Create Date: 2026-02-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # conversations
    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(200), nullable=False, server_default=sa.text("'새 대화'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("message_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("is_bookmarked", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])
    op.create_index("ix_conversations_is_bookmarked", "conversations", ["is_bookmarked"])

    # conversation_messages
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"])

    # user_personas
    op.create_table(
        "user_personas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(100), nullable=False, unique=True),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("expertise_level", sa.String(20), nullable=True),
        sa.Column("expertise_domains", sa.String(500), nullable=True),
        sa.Column("tone", sa.String(20), nullable=True),
        sa.Column("language_style", sa.String(20), nullable=True),
        sa.Column("response_format_preference", sa.String(30), nullable=True),
        sa.Column("additional_context", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_personas_user_id", "user_personas", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_personas")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")

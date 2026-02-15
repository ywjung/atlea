"""Auth tables: sessions, token_blacklist, ip_rate_limits, captcha_challenges

Revision ID: 003
Revises: 002
Create Date: 2026-02-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # sessions
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    # token_blacklist
    op.create_table(
        "token_blacklist",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("reason", sa.String(100), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_token_blacklist_token_hash", "token_blacklist", ["token_hash"])
    op.create_index("ix_token_blacklist_expires_at", "token_blacklist", ["expires_at"])

    # ip_rate_limits
    op.create_table(
        "ip_rate_limits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("endpoint", sa.String(100), nullable=False, server_default="general"),
        sa.Column("request_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("block_reason", sa.Text, nullable=True),
    )
    op.create_index("ix_ip_rate_limits_ip_endpoint", "ip_rate_limits", ["ip_address", "endpoint"], unique=True)
    op.create_index("ix_ip_rate_limits_expires_at", "ip_rate_limits", ["expires_at"])

    # captcha_challenges
    op.create_table(
        "captcha_challenges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("answer", sa.String(50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_captcha_challenges_expires_at", "captcha_challenges", ["expires_at"])

    # password_reset_tokens
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"])
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("captcha_challenges")
    op.drop_table("ip_rate_limits")
    op.drop_table("token_blacklist")
    op.drop_table("sessions")

"""Initial schema — all tables for PostgreSQL migration

Revision ID: 001
Revises:
Create Date: 2026-02-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. organizations (no FK dependencies)
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])

    # 2. users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("org_id", UUID(as_uuid=True), nullable=True),
        sa.Column("org_role", sa.String(20), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("totp_secret", sa.Text, nullable=True),
        sa.Column("totp_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_org_id", "users", ["org_id"])

    # 3. organization_members (N:M)
    op.create_table(
        "organization_members",
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 4. document_groups (self-referential hierarchy)
    op.create_table(
        "document_groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("icon", sa.String(10), nullable=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("document_groups.id", ondelete="CASCADE"), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("updated_by", sa.String(100), nullable=True),
        sa.Column("document_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_document_groups_parent_id", "document_groups", ["parent_id"])

    # 5. group_documents
    op.create_table(
        "group_documents",
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("document_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("filename", sa.String(500), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 6. group_organizations (N:M)
    op.create_table(
        "group_organizations",
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("document_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_root", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )

    # 7. document_versions
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("file_hash", sa.String(128), nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("comment", sa.Text, nullable=False, server_default=""),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("filename", "version_number", name="uq_doc_version"),
    )
    op.create_index("ix_document_versions_filename", "document_versions", ["filename"])

    # 8. document_latest_versions
    op.create_table(
        "document_latest_versions",
        sa.Column("filename", sa.String(500), primary_key=True),
        sa.Column("latest_version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 9. audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # 10. security_logs
    op.create_table(
        "security_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_security_logs_level", "security_logs", ["level"])
    op.create_index("ix_security_logs_event_type", "security_logs", ["event_type"])
    op.create_index("ix_security_logs_user_id", "security_logs", ["user_id"])
    op.create_index("ix_security_logs_created_at", "security_logs", ["created_at"])

    # 11. system_config
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False, server_default="string"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 12. login_history
    op.create_table(
        "login_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("failure_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_login_history_user_id", "login_history", ["user_id"])
    op.create_index("ix_login_history_created_at", "login_history", ["created_at"])

    # 13. webhooks
    op.create_table(
        "webhooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret", sa.Text, nullable=True),
        sa.Column("events", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("headers", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_webhooks_user_id", "webhooks", ["user_id"])

    # 14. feedback_entries
    op.create_table(
        "feedback_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("response", sa.Text, nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_entries_user_id", "feedback_entries", ["user_id"])
    op.create_index("ix_feedback_entries_created_at", "feedback_entries", ["created_at"])


def downgrade() -> None:
    op.drop_table("feedback_entries")
    op.drop_table("webhooks")
    op.drop_table("login_history")
    op.drop_table("system_config")
    op.drop_table("security_logs")
    op.drop_table("audit_logs")
    op.drop_table("document_latest_versions")
    op.drop_table("document_versions")
    op.drop_table("group_organizations")
    op.drop_table("group_documents")
    op.drop_table("document_groups")
    op.drop_table("organization_members")
    op.drop_table("users")
    op.drop_table("organizations")

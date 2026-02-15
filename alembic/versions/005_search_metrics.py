"""Search metrics table

Revision ID: 005
Revises: 004
Create Date: 2026-02-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("search_mode", sa.String(50), nullable=False),
        sa.Column("sources_used", JSONB, nullable=False, server_default="[]"),
        sa.Column("local_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("web_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("docs_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("response_time", sa.Float, nullable=False),
        sa.Column("cache_hit", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("user_id", sa.String(100), nullable=True, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("search_metrics")

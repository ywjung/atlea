"""Cache tables for semantic, embedding, query result, and follow-up caches

Revision ID: 007
Revises: 006
Create Date: 2026-02-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Semantic cache (pgvector similarity search) ───────────────────
    op.create_table(
        "semantic_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("question_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("response", sa.Text, nullable=False),
        sa.Column("sources", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("context", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("top_k", sa.Integer, nullable=False, server_default="5"),
        sa.Column("document_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("group_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_semantic_cache_hash", "semantic_cache", ["question_hash"])
    op.create_index("ix_semantic_cache_expires", "semantic_cache", ["expires_at"])

    # HNSW index for vector cosine similarity search
    op.execute(
        """
        CREATE INDEX ix_semantic_cache_embedding ON semantic_cache
          USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """
    )

    # ── Embedding cache ───────────────────────────────────────────────
    op.create_table(
        "embedding_cache",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("embedding_data", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_embedding_cache_expires", "embedding_cache", ["expires_at"])

    # ── Query result cache ────────────────────────────────────────────
    op.create_table(
        "query_result_cache",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("result", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_query_result_cache_expires", "query_result_cache", ["expires_at"]
    )

    # ── Follow-up cache ───────────────────────────────────────────────
    op.create_table(
        "followup_cache",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("questions", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_followup_cache_expires", "followup_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_table("followup_cache")
    op.drop_table("query_result_cache")
    op.drop_table("embedding_cache")
    op.execute("DROP INDEX IF EXISTS ix_semantic_cache_embedding")
    op.drop_table("semantic_cache")

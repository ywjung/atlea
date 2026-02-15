"""Sentence embeddings table for fine-grained retrieval

Revision ID: 008
Revises: 007
Create Date: 2026-02-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sentence_embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chunk_id",
            UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("index_version", sa.String(100), nullable=False),
        sa.Column("sentence_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sentence_text", sa.Text, nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("group_id", sa.String(200), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # B-tree indexes
    op.create_index("ix_sent_emb_version", "sentence_embeddings", ["index_version"])
    op.create_index("ix_sent_emb_chunk_id", "sentence_embeddings", ["chunk_id"])
    op.create_index("ix_sent_emb_filename", "sentence_embeddings", ["filename"])

    # HNSW index for vector cosine similarity search
    op.execute(
        """
        CREATE INDEX ix_sent_emb_embedding ON sentence_embeddings
          USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.drop_table("sentence_embeddings")

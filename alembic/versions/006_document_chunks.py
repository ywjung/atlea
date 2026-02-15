"""Document chunks table with pgvector and tsvector

Revision ID: 006
Revises: 005
Create Date: 2026-02-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("index_version", sa.String(100), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("source", sa.Text, nullable=True),
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
    op.create_index("ix_chunks_version", "document_chunks", ["index_version"])
    op.create_index("ix_chunks_filename", "document_chunks", ["filename"])

    # HNSW index for vector cosine similarity search
    op.execute(
        """
        CREATE INDEX ix_chunks_embedding ON document_chunks
          USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """
    )

    # tsvector column (maintained by trigger for BM25-style search)
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN text_search tsvector"
    )
    op.execute(
        """
        CREATE INDEX ix_chunks_text_search ON document_chunks
          USING GIN (text_search)
        """
    )

    # Trigger to auto-populate text_search on INSERT/UPDATE
    op.execute(
        """
        CREATE FUNCTION document_chunks_tsvector_update() RETURNS trigger AS $$
        BEGIN
            NEW.text_search := to_tsvector('simple', COALESCE(NEW.text, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_chunks_tsvector
          BEFORE INSERT OR UPDATE OF text ON document_chunks
          FOR EACH ROW EXECUTE FUNCTION document_chunks_tsvector_update()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsvector ON document_chunks")
    op.execute("DROP FUNCTION IF EXISTS document_chunks_tsvector_update()")
    op.drop_table("document_chunks")

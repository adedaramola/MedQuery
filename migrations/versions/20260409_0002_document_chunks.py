"""Add document_chunks table for uploaded PDF/DOCX/TXT files

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-09 00:00:00
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

VECTOR_DIM = 1536   # text-embedding-3-small


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id          TEXT PRIMARY KEY,
            content     TEXT NOT NULL,
            embedding   vector({VECTOR_DIM}),
            metadata    JSONB,
            filename    TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
        ON document_chunks USING hnsw (embedding vector_cosine_ops)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_filename
        ON document_chunks(filename)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_chunks")

"""Initial schema: pgvector extension, medical_qna, medical_device, conversation_turns

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

VECTOR_DIM = 1536   # text-embedding-3-small


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS medical_qna (
            id        TEXT PRIMARY KEY,
            content   TEXT NOT NULL,
            embedding vector({VECTOR_DIM}),
            metadata  JSONB
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS medical_device (
            id        TEXT PRIMARY KEY,
            content   TEXT NOT NULL,
            embedding vector({VECTOR_DIM}),
            metadata  JSONB
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id              SERIAL PRIMARY KEY,
            conversation_id TEXT      NOT NULL,
            role            TEXT      NOT NULL,
            content         TEXT      NOT NULL,
            created_at      TIMESTAMP DEFAULT NOW()
        )
    """)

    # Indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_medical_qna_embedding
        ON medical_qna USING hnsw (embedding vector_cosine_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_medical_device_embedding
        ON medical_device USING hnsw (embedding vector_cosine_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_conv_id
        ON conversation_turns(conversation_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation_turns")
    op.execute("DROP TABLE IF EXISTS medical_device")
    op.execute("DROP TABLE IF EXISTS medical_qna")
    # Note: we do NOT drop the vector extension as other tables may use it

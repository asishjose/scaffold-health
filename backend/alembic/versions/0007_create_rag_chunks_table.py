"""create rag chunks table

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSIONS = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "rag_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patients.id"),
            nullable=True,
        ),
        sa.Column(
            "therapist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("therapists.id"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("embedding_model", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=32), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope IN ('patient_notes', 'clinical_guidelines', 'patient_education')",
            name="ck_rag_chunks_scope",
        ),
    )
    op.create_index("ix_rag_chunks_scope", "rag_chunks", ["scope"])
    op.create_index("ix_rag_chunks_patient_id", "rag_chunks", ["patient_id"])
    op.create_index("ix_rag_chunks_therapist_id", "rag_chunks", ["therapist_id"])
    op.create_index("ix_rag_chunks_source_document_id", "rag_chunks", ["source_document_id"])
    # No ivfflat/hnsw index at MVP scale — the corpus is realistically dozens
    # to low hundreds of rows, and pgvector's own guidance is that ANN
    # indexes only pay off in the thousands+ row range. A plain sequential
    # scan over the cosine-distance operator is both simpler and faster
    # below that threshold. Add one in a future migration once corpus size
    # warrants it.


def downgrade() -> None:
    op.drop_index("ix_rag_chunks_source_document_id", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_therapist_id", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_patient_id", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_scope", table_name="rag_chunks")
    op.drop_table("rag_chunks")

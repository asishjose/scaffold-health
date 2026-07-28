import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.llm_client import EMBEDDING_DIMENSIONS
from app.rag.events import (
    SCOPE_CLINICAL_GUIDELINES,
    SCOPE_PATIENT_EDUCATION,
    SCOPE_PATIENT_NOTES,
)


class RagChunk(Base):
    """Read model projected from `RagChunksIndexed` events — one row per
    embedded chunk. Never written to directly; only by the rag projector.
    `patient_id`/`therapist_id` are null for the two shared corpora
    (clinical_guidelines, patient_education), which aren't scoped to a
    patient (PRD §6.4).
    """

    __tablename__ = "rag_chunks"
    __table_args__ = (
        CheckConstraint(
            f"scope IN ('{SCOPE_PATIENT_NOTES}', '{SCOPE_CLINICAL_GUIDELINES}', "
            f"'{SCOPE_PATIENT_EDUCATION}')",
            name="ck_rag_chunks_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Denormalized owner columns for query-level RBAC (same pattern as
    # Document.therapist_id / ProfileField.therapist_id), nullable because
    # the shared corpora have no single owning patient/therapist.
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=True, index=True
    )
    therapist_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.id"), nullable=True, index=True
    )

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True, index=True
    )
    # Document filename, or seed filename for the shared corpora.
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # The RagChunksIndexed event this row is a projection of.
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

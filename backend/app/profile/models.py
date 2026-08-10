import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProfileField(Base):
    """Read model projected from `ProfileFieldsMerged` events — one row per
    atomic extracted fact. Never written to directly; only by the profile
    projector. Rows are never updated or deleted: an overwrite-strategy
    field supersedes its prior rows (`superseded_at` set) rather than
    mutating them, so point-in-time history is always recoverable by replay.
    """

    __tablename__ = "profile_fields"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    # Denormalized from patient.therapist_id at merge time, same pattern as
    # Document, so RBAC is enforced by filtering the query itself.
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.id"), nullable=False, index=True
    )

    field_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    # The ProfileFieldsMerged event this row is a projection of — the
    # "causing event" referenced by every profile version (PRD §6.3).
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    is_contradiction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once a therapist reviews a contradiction via ContradictionAcknowledged
    # (PRD §6.3 exception: the one needs_review reason that isn't purely
    # derived, since a contradiction must be explicitly decided, not time out).
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

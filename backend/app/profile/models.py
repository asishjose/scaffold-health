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

    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PendingProfileFact(Base):
    """A candidate fact from extraction that contradicts the patient's
    immutable baseline or fell below the confidence bar — held here, NOT
    projected from an event, until a therapist approves or rejects it.
    An unverified LLM guess isn't a confirmed clinical fact yet, so it
    deliberately sits outside the event-sourced history until a therapist
    acts on it; only `resolve_pending_fact` in profile/commands.py writes
    to this table, and approval is what finally appends the real
    ProfileFieldsMerged event via the same merge path as auto-merged facts.
    """

    __tablename__ = "pending_profile_facts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.id"), nullable=False, index=True
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )

    field_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_quote: Mapped[str] = mapped_column(Text, nullable=False)

    # A fact can be staged for either reason, or both.
    is_contradiction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_low_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.id"), nullable=True
    )
    # Final value used on approval (== value unless the therapist edited it);
    # null while pending or rejected.
    resolved_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_profile_field_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profile_fields.id"), nullable=True
    )

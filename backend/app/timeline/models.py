import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ENTRY_TYPE_PHASE_ADVANCE = "phase_advance"
ENTRY_TYPE_MILESTONE = "milestone"
ENTRY_TYPE_DOCUMENT_EXTRACTED = "document_extracted"


class TimelineEntry(Base):
    """Read model projected from `PatientPhaseAdvanced` (patients),
    `DocumentTextExtracted` (documents), and `ProfileFieldsMerged` events
    filtered to field_name == "milestones" (profile). Never written to
    directly; only by the timeline projector.
    """

    __tablename__ = "timeline_entries"
    __table_args__ = (
        CheckConstraint(
            f"entry_type IN ('{ENTRY_TYPE_PHASE_ADVANCE}', '{ENTRY_TYPE_MILESTONE}', "
            f"'{ENTRY_TYPE_DOCUMENT_EXTRACTED}')",
            name="ck_timeline_entries_entry_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    # Denormalized for query-level RBAC (same pattern as Document.therapist_id
    # / ProfileField.therapist_id / RagChunk.therapist_id).
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.id"), nullable=False, index=True
    )

    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # The causing event's created_at — the chronological sort key for the
    # timeline, distinct from `created_at` below (row-insertion bookkeeping).
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Entry-type-specific fields (from_phase/to_phase/note for phase_advance;
    # value/confidence/source_quote/source_document_id for milestone;
    # filename/document_id for document_extracted). Kept as JSONB rather than
    # typed nullable columns since the three shapes are disjoint and nothing
    # queries into this column at the SQL level.
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # The event this row is a projection of. No FK constraint, matching
    # ProfileField.source_event_id / RagChunk.source_event_id.
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

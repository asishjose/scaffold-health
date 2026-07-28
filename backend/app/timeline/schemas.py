import uuid
from datetime import datetime

from pydantic import BaseModel

from app.timeline.models import TimelineEntry


class TimelineEntryResponse(BaseModel):
    """Full therapist-facing view — includes provenance."""

    id: uuid.UUID
    entry_type: str
    occurred_at: datetime
    from_phase: str | None = None
    to_phase: str | None = None
    note: str | None = None
    value: str | None = None
    confidence: float | None = None
    source_quote: str | None = None
    source_document_id: str | None = None
    filename: str | None = None
    document_id: str | None = None


class TimelinePortalEntryResponse(BaseModel):
    """Reduced patient-facing view: no provenance/confidence/source-document
    detail (PRD §5.8).
    """

    id: uuid.UUID
    entry_type: str
    occurred_at: datetime
    from_phase: str | None = None
    to_phase: str | None = None
    note: str | None = None
    value: str | None = None
    filename: str | None = None


def build_timeline_entry_response(entry: TimelineEntry) -> TimelineEntryResponse:
    detail = entry.detail
    return TimelineEntryResponse(
        id=entry.id,
        entry_type=entry.entry_type,
        occurred_at=entry.occurred_at,
        from_phase=detail.get("from_phase"),
        to_phase=detail.get("to_phase"),
        note=detail.get("note"),
        value=detail.get("value"),
        confidence=detail.get("confidence"),
        source_quote=detail.get("source_quote"),
        source_document_id=detail.get("source_document_id"),
        filename=detail.get("filename"),
        document_id=detail.get("document_id"),
    )


def build_timeline_portal_entry_response(entry: TimelineEntry) -> TimelinePortalEntryResponse:
    detail = entry.detail
    return TimelinePortalEntryResponse(
        id=entry.id,
        entry_type=entry.entry_type,
        occurred_at=entry.occurred_at,
        from_phase=detail.get("from_phase"),
        to_phase=detail.get("to_phase"),
        note=detail.get("note"),
        value=detail.get("value"),
        filename=detail.get("filename"),
    )

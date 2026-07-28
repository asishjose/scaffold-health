import uuid

from sqlalchemy.orm import Session

from app.documents.events import DOCUMENT_TEXT_EXTRACTED
from app.documents.models import Document
from app.event_store.models import Event
from app.patients.events import PATIENT_PHASE_ADVANCED
from app.profile.events import PROFILE_FIELDS_MERGED
from app.timeline.models import (
    ENTRY_TYPE_DOCUMENT_EXTRACTED,
    ENTRY_TYPE_MILESTONE,
    ENTRY_TYPE_PHASE_ADVANCE,
    TimelineEntry,
)


def apply(db: Session, event: Event) -> list[TimelineEntry]:
    """Applies one causing event to the timeline_entries read model. Called
    synchronously right after the event is appended by the patients/
    documents/profile command handlers, and (eventually) by full replay.
    Returns a list — like profile.projector.apply — because one
    ProfileFieldsMerged event can carry a batch of milestone facts, each
    becoming its own row.
    """
    if event.event_type == PATIENT_PHASE_ADVANCED:
        return [_apply_phase_advanced(db, event)]
    if event.event_type == DOCUMENT_TEXT_EXTRACTED:
        return [_apply_document_extracted(db, event)]
    if event.event_type == PROFILE_FIELDS_MERGED:
        return _apply_profile_fields_merged(db, event)
    return []


def _apply_phase_advanced(db: Session, event: Event) -> TimelineEntry:
    payload = event.payload
    entry = TimelineEntry(
        id=uuid.uuid4(),
        patient_id=event.stream_id,
        therapist_id=event.actor_id,
        entry_type=ENTRY_TYPE_PHASE_ADVANCE,
        occurred_at=event.created_at,
        detail={
            "from_phase": payload["from_phase"],
            "to_phase": payload["to_phase"],
            "note": payload["note"],
        },
        source_event_id=event.id,
    )
    db.add(entry)
    db.flush()
    return entry


def _apply_document_extracted(db: Session, event: Event) -> TimelineEntry:
    document = db.get(Document, event.stream_id)
    entry = TimelineEntry(
        id=uuid.uuid4(),
        patient_id=document.patient_id,
        therapist_id=document.therapist_id,
        entry_type=ENTRY_TYPE_DOCUMENT_EXTRACTED,
        occurred_at=event.created_at,
        detail={"filename": document.filename, "document_id": str(document.id)},
        source_event_id=event.id,
    )
    db.add(entry)
    db.flush()
    return entry


def _apply_profile_fields_merged(db: Session, event: Event) -> list[TimelineEntry]:
    payload = event.payload
    if payload["field_name"] != "milestones":
        return []

    source_document_id = payload.get("source_document_id")

    entries = []
    for fact in payload["facts"]:
        entry = TimelineEntry(
            id=uuid.uuid4(),
            patient_id=event.stream_id,
            therapist_id=uuid.UUID(payload["therapist_id"]),
            entry_type=ENTRY_TYPE_MILESTONE,
            occurred_at=event.created_at,
            detail={
                "value": fact["value"],
                "confidence": fact.get("confidence"),
                "source_quote": fact.get("source_quote"),
                "source_document_id": source_document_id,
            },
            source_event_id=event.id,
        )
        db.add(entry)
        entries.append(entry)

    db.flush()
    return entries

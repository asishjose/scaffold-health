import uuid

from sqlalchemy.orm import Session

from app.documents.events import (
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_TEXT_EXTRACTED,
    DOCUMENT_UPLOADED,
    STATUS_EXTRACTED,
    STATUS_FAILED,
    STATUS_PROCESSING,
)
from app.documents.models import Document
from app.event_store.models import Event


def apply(db: Session, event: Event) -> Document | None:
    """Applies one event to the documents read model. Called synchronously
    right after the causing event is appended, and (eventually) by full
    replay.
    """
    if event.event_type == DOCUMENT_UPLOADED:
        return _apply_document_uploaded(db, event)
    if event.event_type == DOCUMENT_TEXT_EXTRACTED:
        return _apply_document_text_extracted(db, event)
    if event.event_type == DOCUMENT_EXTRACTION_FAILED:
        return _apply_document_extraction_failed(db, event)
    return None


def _apply_document_uploaded(db: Session, event: Event) -> Document:
    payload = event.payload
    document = Document(
        id=event.stream_id,
        patient_id=uuid.UUID(payload["patient_id"]),
        therapist_id=uuid.UUID(payload["therapist_id"]),
        filename=payload["filename"],
        content_type=payload["content_type"],
        storage_path=payload["storage_path"],
        status=STATUS_PROCESSING,
    )
    db.add(document)
    db.flush()
    return document


def _apply_document_text_extracted(db: Session, event: Event) -> Document:
    document = db.get(Document, event.stream_id)
    document.status = STATUS_EXTRACTED
    document.extracted_text = event.payload["extracted_text"]
    document.extracted_at = event.created_at
    db.flush()
    return document


def _apply_document_extraction_failed(db: Session, event: Event) -> Document:
    document = db.get(Document, event.stream_id)
    document.status = STATUS_FAILED
    document.error = event.payload["error"]
    db.flush()
    return document

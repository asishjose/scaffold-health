import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.documents import projector
from app.documents.events import (
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_TEXT_EXTRACTED,
    DOCUMENT_UPLOADED,
    STREAM_TYPE_DOCUMENT,
)
from app.documents.models import Document
from app.event_store.store import append_event
from app.patients.models import Patient
from app.timeline import projector as timeline_projector

PDF_MAGIC_BYTES = b"%PDF-"


class PatientNotFound(Exception):
    pass


class InvalidFileType(Exception):
    pass


def upload_document(
    db: Session,
    *,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> Document:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.therapist_id == therapist_id)
    ).scalar_one_or_none()
    if patient is None:
        raise PatientNotFound()

    if not filename.lower().endswith(".pdf") or not file_bytes.startswith(PDF_MAGIC_BYTES):
        raise InvalidFileType()

    document_id = uuid.uuid4()
    storage_dir = Path(settings.documents_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{document_id}.pdf"
    storage_path.write_bytes(file_bytes)

    event = append_event(
        db,
        stream_id=document_id,
        stream_type=STREAM_TYPE_DOCUMENT,
        event_type=DOCUMENT_UPLOADED,
        payload={
            "patient_id": str(patient_id),
            "therapist_id": str(therapist_id),
            "filename": filename,
            "content_type": content_type,
            "storage_path": str(storage_path),
        },
        actor_id=therapist_id,
        actor_role="therapist",
    )
    document = projector.apply(db, event)
    db.commit()

    # Deferred import: documents.tasks imports record_extraction_result/
    # record_extraction_failure from this module, so importing it at module
    # scope would create a cycle.
    from app.documents.tasks import process_document

    process_document.delay(str(document.id))

    return document


def record_extraction_result(
    db: Session, *, document_id: uuid.UUID, extracted_text: str
) -> Document:
    event = append_event(
        db,
        stream_id=document_id,
        stream_type=STREAM_TYPE_DOCUMENT,
        event_type=DOCUMENT_TEXT_EXTRACTED,
        payload={"extracted_text": extracted_text},
    )
    document = projector.apply(db, event)
    timeline_projector.apply(db, event)
    db.commit()
    return document


def record_extraction_failure(db: Session, *, document_id: uuid.UUID, error: str) -> Document:
    event = append_event(
        db,
        stream_id=document_id,
        stream_type=STREAM_TYPE_DOCUMENT,
        event_type=DOCUMENT_EXTRACTION_FAILED,
        payload={"error": error},
    )
    document = projector.apply(db, event)
    db.commit()
    return document

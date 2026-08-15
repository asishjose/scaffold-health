import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_trace_id
from app.documents import projector, storage
from app.documents.events import (
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_TEXT_EXTRACTED,
    DOCUMENT_UPLOADED,
    STREAM_TYPE_DOCUMENT,
)
from app.documents.models import Document
from app.event_store.store import append_event
from app.patients.models import Patient
from app.profile.events import PENDING_STATUS_PENDING
from app.profile.models import PendingProfileFact
from app.rag.models import RagChunk
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
    storage_path = storage.save_document_bytes(document_id, file_bytes)

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
            "storage_path": storage_path,
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

    process_document.delay(str(document.id), trace_id=get_trace_id())

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


def maybe_trigger_deferred_rag_indexing(db: Session, *, document_id: uuid.UUID) -> None:
    """Called after a pending fact is resolved (profile.commands). If this
    was the document's last unresolved pending fact, dispatches the
    RAG-indexing task that was skipped at initial processing time
    (documents.tasks.process_document) because unverified content must not
    be Copilot-searchable yet.
    """
    still_pending = db.execute(
        select(PendingProfileFact.id)
        .where(
            PendingProfileFact.source_document_id == document_id,
            PendingProfileFact.status == PENDING_STATUS_PENDING,
        )
        .limit(1)
    ).scalar_one_or_none()
    if still_pending is not None:
        return

    # Idempotency guard: two pending facts for the same document could
    # resolve concurrently and both observe "none left pending".
    already_indexed = db.execute(
        select(RagChunk.id).where(RagChunk.source_document_id == document_id).limit(1)
    ).scalar_one_or_none()
    if already_indexed is not None:
        return

    # Deferred import: documents.tasks imports commands (this module) at
    # module scope, so importing it here at module scope would cycle.
    from app.documents.tasks import run_deferred_rag_indexing

    run_deferred_rag_indexing.delay(str(document_id), trace_id=get_trace_id())


def list_document_ids_with_pending_facts(
    db: Session, *, document_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Bulk version of the pending-check above, for listing endpoints that
    need a has_pending_facts flag per document without one query each.
    """
    if not document_ids:
        return set()
    return set(
        db.execute(
            select(PendingProfileFact.source_document_id)
            .where(
                PendingProfileFact.source_document_id.in_(document_ids),
                PendingProfileFact.status == PENDING_STATUS_PENDING,
            )
            .distinct()
        ).scalars()
    )

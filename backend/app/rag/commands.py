import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.llm_client import embed_text
from app.documents.models import Document
from app.event_store.models import Event
from app.event_store.store import append_event
from app.patients.models import Patient
from app.profile.models import ProfileField
from app.rag import projector
from app.rag.allowlist import is_allowlist_violation
from app.rag.chunking import chunk_text
from app.rag.events import (
    CHUNKER_VERSION,
    EMBEDDING_MODEL,
    RAG_CHUNKS_INDEXED,
    STREAM_TYPE_RAG_INDEX,
)
from app.rag.models import RagChunk

logger = logging.getLogger(__name__)


def index_document_residual_text(
    db: Session, *, patient: Patient, document: Document, text: str
) -> list[RagChunk]:
    """Chunks and embeds the residual (unstructured) text of a document
    into the per-patient notes index, after structured-fact extraction has
    already run (PRD §5.4 step 8). Chunks that near-exact-match a known
    structured field or PHI value are rejected and logged, never embedded
    (PRD §6.4).
    """
    known_values = _known_values_for_patient(db, patient)
    accepted = _chunk_and_embed(
        text,
        reject=lambda chunk: is_allowlist_violation(chunk, known_values),
        log_context=f"patient_id={patient.id} document_id={document.id}",
    )
    if not accepted:
        return []

    event = append_event(
        db,
        stream_id=document.id,
        stream_type=STREAM_TYPE_RAG_INDEX,
        event_type=RAG_CHUNKS_INDEXED,
        payload={
            "scope": "patient_notes",
            "patient_id": str(patient.id),
            "therapist_id": str(patient.therapist_id),
            "source_type": "document",
            "source_document_id": str(document.id),
            "source_label": document.filename,
            "embedding_model": EMBEDDING_MODEL,
            "chunker_version": CHUNKER_VERSION,
            "chunks": accepted,
        },
    )
    rows = projector.apply(db, event)
    db.commit()
    return rows


def seed_shared_corpus(
    db: Session, *, scope: str, source_type: str, label: str, text: str
) -> list[RagChunk]:
    """Chunks and embeds a shared-corpus seed file (clinical guidelines or
    patient education — not scoped to any patient). Idempotent per
    (scope, label): re-running the seed script is a safe no-op that doesn't
    re-call the embedding API.
    """
    idempotency_key = f"rag-seed:{scope}:{label}"
    existing_event = db.execute(
        select(Event).where(Event.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing_event is not None:
        return list(
            db.execute(
                select(RagChunk).where(RagChunk.source_event_id == existing_event.id)
            ).scalars()
        )

    accepted = _chunk_and_embed(text, reject=lambda chunk: None, log_context=f"scope={scope} label={label}")
    if not accepted:
        return []

    event = append_event(
        db,
        stream_id=uuid.uuid4(),
        stream_type=STREAM_TYPE_RAG_INDEX,
        event_type=RAG_CHUNKS_INDEXED,
        payload={
            "scope": scope,
            "patient_id": None,
            "therapist_id": None,
            "source_type": source_type,
            "source_document_id": None,
            "source_label": label,
            "embedding_model": EMBEDDING_MODEL,
            "chunker_version": CHUNKER_VERSION,
            "chunks": accepted,
        },
        idempotency_key=idempotency_key,
    )
    rows = projector.apply(db, event)
    db.commit()
    return rows


def _chunk_and_embed(text: str, *, reject, log_context: str) -> list[dict]:
    accepted: list[dict] = []
    for index, chunk in enumerate(chunk_text(text)):
        violation = reject(chunk)
        if violation is not None:
            logger.warning(
                "rag allowlist rejected chunk %d (%s): near-exact match of known value",
                index,
                log_context,
            )
            continue
        embedding = embed_text(chunk)
        accepted.append({"chunk_index": index, "chunk_text": chunk, "embedding": embedding})
    return accepted


def _known_values_for_patient(db: Session, patient: Patient) -> set[str]:
    """Structured field + raw PHI/identifier values that must never be
    re-embedded as prose (PRD §6.4).
    """
    known: set[str] = {
        patient.name,
        patient.contact_email,
        patient.date_of_birth.isoformat(),
        patient.injury,
        patient.surgery_date.isoformat(),
        patient.current_phase,
    }
    profile_values = db.execute(
        select(ProfileField.value).where(
            ProfileField.patient_id == patient.id,
            ProfileField.superseded_at.is_(None),
        )
    ).scalars()
    known.update(profile_values)
    return {v for v in known if v}

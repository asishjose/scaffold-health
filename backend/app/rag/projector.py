import uuid

from sqlalchemy.orm import Session

from app.event_store.models import Event
from app.rag.events import RAG_CHUNKS_INDEXED
from app.rag.models import RagChunk


def apply(db: Session, event: Event) -> list[RagChunk]:
    """Applies one event to the rag_chunks read model. Called synchronously
    right after the causing event is appended, and (eventually) by full
    replay. Never re-computes embeddings — the vector for each chunk was
    already computed by the command handler and is stored in the event
    payload, since an external embedding API is not guaranteed to return
    bit-identical vectors across calls.
    """
    if event.event_type == RAG_CHUNKS_INDEXED:
        return _apply_rag_chunks_indexed(db, event)
    return []


def _apply_rag_chunks_indexed(db: Session, event: Event) -> list[RagChunk]:
    payload = event.payload
    patient_id = payload.get("patient_id")
    therapist_id = payload.get("therapist_id")
    source_document_id = payload.get("source_document_id")

    rows = []
    for chunk in payload["chunks"]:
        row = RagChunk(
            id=uuid.uuid4(),
            scope=payload["scope"],
            patient_id=uuid.UUID(patient_id) if patient_id else None,
            therapist_id=uuid.UUID(therapist_id) if therapist_id else None,
            source_type=payload["source_type"],
            source_document_id=uuid.UUID(source_document_id) if source_document_id else None,
            source_label=payload.get("source_label"),
            chunk_index=chunk["chunk_index"],
            chunk_text=chunk["chunk_text"],
            embedding=chunk["embedding"],
            embedding_model=payload["embedding_model"],
            chunker_version=payload["chunker_version"],
            source_event_id=event.id,
        )
        db.add(row)
        rows.append(row)
    return rows

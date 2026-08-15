import io
import logging
import uuid
from datetime import datetime, timezone

from celery.exceptions import Retry
from pypdf import PdfReader

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.llm_client import LLMExtractionError, extract_facts
from app.core.logging_config import bind_context
from app.documents import commands, storage
from app.documents.models import Document
from app.patients.models import Patient
from app.profile.commands import MergeResult, merge_extracted_facts
from app.profile.events import EXTRACTABLE_FIELDS
from app.rag import commands as rag_commands

logger = logging.getLogger(__name__)

RETRYABLE_COUNTDOWN_SECONDS = 30


@celery_app.task(name="documents.process_document", bind=True, max_retries=3)
def process_document(self, document_id: str, trace_id: str | None = None) -> None:
    """Extracts raw text from an uploaded PDF, runs LLM fact extraction over
    it, and merges the results into the patient's Knowledge Profile
    (PRD §5.4). A failure at any step — OCR/text extraction, the LLM call,
    or an invalid response — marks the document "failed"; nothing is
    considered "extracted" until the whole pipeline has succeeded.

    LLM calls can fail transiently (DNS blips, timeouts, rate limits), so
    LLMExtractionError gets retried with backoff before giving up; other
    failures (e.g. a corrupt PDF) are permanent and fail immediately.

    `trace_id` carries the id of the upload request that dispatched this
    task, so worker logs can be correlated back to it even without a
    tracing backend in place yet; it falls back to this task's own id
    (e.g. on a retry, where no request is on the stack).
    """
    bind_context(request_id=self.request.id, trace_id=trace_id or self.request.id)
    logger.info("document processing started", extra={"document_id": document_id})
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        patient = db.get(Patient, document.patient_id)
        text = _extract_text(document.storage_path)
        result = _run_fact_extraction(db, patient=patient, document=document, text=text)
        if result is None or not result.staged:
            _run_rag_indexing(db, patient=patient, document=document, text=text)
        # else: at least one fact is pending review — indexing is deferred
        # until it's resolved (documents.commands.maybe_trigger_deferred_rag_indexing),
        # so unverified document content never becomes Copilot-searchable.
        commands.record_extraction_result(db, document_id=document.id, extracted_text=text)
        logger.info("document processing completed", extra={"document_id": document_id})
    except LLMExtractionError as exc:
        db.rollback()
        if self.request.retries < self.max_retries:
            countdown = RETRYABLE_COUNTDOWN_SECONDS * (2**self.request.retries)
            try:
                raise self.retry(exc=exc, countdown=countdown)
            except Retry:
                # Real retry signal from a worker context — let it propagate
                # so Celery re-enqueues the task; don't record a failure yet.
                logger.warning(
                    "document processing retrying",
                    extra={"document_id": document_id, "retry": self.request.retries, "error": str(exc)},
                )
                raise
            except Exception:
                # self.retry() re-raises `exc` itself instead of a Retry
                # when the task is called directly rather than through a
                # worker (Task.request.called_directly) — e.g. in tests.
                # There's no broker to re-enqueue against, so fall through
                # and record it as failed like any other terminal error.
                pass
        logger.error(
            "document processing failed", extra={"document_id": document_id, "error": str(exc)}
        )
        commands.record_extraction_failure(db, document_id=uuid.UUID(document_id), error=str(exc))
    except Exception as exc:
        db.rollback()
        logger.exception("document processing failed", extra={"document_id": document_id})
        commands.record_extraction_failure(db, document_id=uuid.UUID(document_id), error=str(exc))
    finally:
        db.close()


def _extract_text(storage_path: str) -> str:
    file_bytes = storage.read_document_bytes(storage_path)
    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _run_fact_extraction(
    db, *, patient: Patient, document: Document, text: str
) -> MergeResult | None:
    if not text.strip():
        return None

    facts = extract_facts(text, schema=EXTRACTABLE_FIELDS)
    if not facts:
        return None

    return merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=facts,
        extracted_at=datetime.now(timezone.utc),
    )


def _run_rag_indexing(db, *, patient: Patient, document: Document, text: str) -> None:
    """Indexes residual (unstructured) document text into the per-patient
    RAG index (PRD §5.4 step 8). Indexing failures (e.g. a transient
    embedding-API hiccup) are logged and swallowed rather than propagated —
    they must never turn an otherwise-successful structured extraction into
    a "failed" document.
    """
    if not text.strip():
        return

    try:
        rag_commands.index_document_residual_text(db, patient=patient, document=document, text=text)
    except Exception as exc:
        db.rollback()
        logger.warning("rag indexing failed for document=%s: %s", document.id, exc)


@celery_app.task(name="documents.run_deferred_rag_indexing", bind=True)
def run_deferred_rag_indexing(self, document_id: str, trace_id: str | None = None) -> None:
    """Runs the RAG indexing that was skipped at upload time because the
    document produced at least one pending fact. Dispatched once that
    document's last pending fact is resolved (approved or rejected) — see
    documents.commands.maybe_trigger_deferred_rag_indexing.
    """
    bind_context(request_id=self.request.id, trace_id=trace_id or self.request.id)
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None or not document.extracted_text:
            return
        patient = db.get(Patient, document.patient_id)
        _run_rag_indexing(db, patient=patient, document=document, text=document.extracted_text)
    finally:
        db.close()

import uuid
from datetime import datetime, timezone

from pypdf import PdfReader

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.llm_client import extract_facts
from app.documents import commands
from app.documents.models import Document
from app.patients.models import Patient
from app.profile.commands import merge_extracted_facts
from app.profile.events import EXTRACTABLE_FIELDS


@celery_app.task(name="documents.process_document")
def process_document(document_id: str) -> None:
    """Extracts raw text from an uploaded PDF, runs LLM fact extraction over
    it, and merges the results into the patient's Knowledge Profile
    (PRD §5.4). A failure at any step — OCR/text extraction, the LLM call,
    or an invalid response — marks the document "failed"; nothing is
    considered "extracted" until the whole pipeline has succeeded.
    """
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        text = _extract_text(document.storage_path)
        _run_fact_extraction(db, document=document, text=text)
        commands.record_extraction_result(db, document_id=document.id, extracted_text=text)
    except Exception as exc:
        db.rollback()
        commands.record_extraction_failure(db, document_id=uuid.UUID(document_id), error=str(exc))
    finally:
        db.close()


def _extract_text(storage_path: str) -> str:
    reader = PdfReader(storage_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _run_fact_extraction(db, *, document: Document, text: str) -> None:
    if not text.strip():
        return

    patient = db.get(Patient, document.patient_id)
    facts = extract_facts(text, schema=EXTRACTABLE_FIELDS)
    if not facts:
        return

    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=facts,
        extracted_at=datetime.now(timezone.utc),
    )

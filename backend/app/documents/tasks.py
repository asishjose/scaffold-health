import uuid

from pypdf import PdfReader

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.documents import commands
from app.documents.models import Document


@celery_app.task(name="documents.process_document")
def process_document(document_id: str) -> None:
    """Extracts raw text from an uploaded PDF and records the result.

    This is deliberately not the full LLM-based structured-fact extraction
    described in the PRD (that requires a Gemini API key and the Knowledge
    Builder merge engine, neither of which exist yet) — it proves out the
    upload -> async processing -> status transition pipeline with real,
    deterministic text extraction.
    """
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        text = _extract_text(document.storage_path)
        commands.record_extraction_result(db, document_id=document.id, extracted_text=text)
    except Exception as exc:
        db.rollback()
        commands.record_extraction_failure(db, document_id=uuid.UUID(document_id), error=str(exc))
    finally:
        db.close()


def _extract_text(storage_path: str) -> str:
    reader = PdfReader(storage_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)

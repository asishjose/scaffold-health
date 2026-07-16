import uuid
from datetime import date, timedelta
from io import BytesIO

from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.core.config import settings
from app.core.db import SessionLocal
from app.documents import commands
from app.documents.models import Document
from app.documents.tasks import process_document
from app.patients import commands as patient_commands


def _minimal_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_patient(db: Session) -> tuple[uuid.UUID, uuid.UUID]:
    therapist = auth_commands.register_therapist(
        db,
        name="Dana Therapist",
        email=f"therapist-{uuid.uuid4()}@example.com",
        password="a-strong-password",
        registration_code=settings.clinic_registration_code,
    )
    patient = patient_commands.create_patient(
        db,
        therapist_id=therapist.id,
        name="Pat Patient",
        date_of_birth=date(1990, 1, 1),
        contact_email=f"patient-{uuid.uuid4()}@example.com",
        surgery_date=date.today() + timedelta(days=14),
    )
    return therapist.id, patient.id


def test_process_document_extracts_text_and_marks_extracted(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_minimal_pdf_bytes(),
    )

    # Runs the task body directly (not via .delay()/broker) so the test
    # doesn't depend on a live Celery worker process.
    process_document(str(document.id))

    fresh_session = SessionLocal()
    try:
        refreshed = fresh_session.get(Document, document.id)
        assert refreshed.status == "extracted"
        assert refreshed.extracted_text is not None
        assert refreshed.extracted_at is not None
    finally:
        fresh_session.close()


def test_process_document_marks_failed_on_corrupt_storage_path(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_minimal_pdf_bytes(),
    )
    db.commit()

    # Simulate the stored file having gone missing/corrupt on disk.
    fresh_session = SessionLocal()
    try:
        row = fresh_session.get(Document, document.id)
        row.storage_path = "/nonexistent/path.pdf"
        fresh_session.commit()
    finally:
        fresh_session.close()

    process_document(str(document.id))

    verify_session = SessionLocal()
    try:
        refreshed = verify_session.get(Document, document.id)
        assert refreshed.status == "failed"
        assert refreshed.error
    finally:
        verify_session.close()

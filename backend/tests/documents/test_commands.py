import uuid
from datetime import date, timedelta
from io import BytesIO

import pytest
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.core.config import settings
from app.documents import commands
from app.event_store.store import get_stream_events
from app.patients import commands as patient_commands


def _minimal_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_patient(db: Session) -> uuid.UUID:
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


def test_upload_document_appends_event_and_projects_read_model(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)

    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_minimal_pdf_bytes(),
    )

    assert document.status == "processing"
    assert document.patient_id == patient_id
    assert document.therapist_id == therapist_id

    events = get_stream_events(db, stream_id=document.id)
    assert len(events) == 1
    assert events[0].event_type == "DocumentUploaded"


def test_upload_document_rejects_non_owning_therapist(db: Session) -> None:
    _, patient_id = _make_patient(db)
    other_therapist_id, _ = _make_patient(db)

    with pytest.raises(commands.PatientNotFound):
        commands.upload_document(
            db,
            patient_id=patient_id,
            therapist_id=other_therapist_id,
            filename="mri-report.pdf",
            content_type="application/pdf",
            file_bytes=_minimal_pdf_bytes(),
        )


def test_upload_document_rejects_unknown_patient(db: Session) -> None:
    therapist_id, _ = _make_patient(db)

    with pytest.raises(commands.PatientNotFound):
        commands.upload_document(
            db,
            patient_id=uuid.uuid4(),
            therapist_id=therapist_id,
            filename="mri-report.pdf",
            content_type="application/pdf",
            file_bytes=_minimal_pdf_bytes(),
        )


def test_upload_document_rejects_non_pdf_extension(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)

    with pytest.raises(commands.InvalidFileType):
        commands.upload_document(
            db,
            patient_id=patient_id,
            therapist_id=therapist_id,
            filename="notes.txt",
            content_type="application/pdf",
            file_bytes=_minimal_pdf_bytes(),
        )


def test_upload_document_rejects_spoofed_content_not_actually_pdf(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)

    with pytest.raises(commands.InvalidFileType):
        commands.upload_document(
            db,
            patient_id=patient_id,
            therapist_id=therapist_id,
            filename="fake.pdf",
            content_type="application/pdf",
            file_bytes=b"not actually a pdf",
        )


def test_record_extraction_result_marks_document_extracted(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_minimal_pdf_bytes(),
    )

    updated = commands.record_extraction_result(
        db, document_id=document.id, extracted_text="hello world"
    )

    assert updated.status == "extracted"
    assert updated.extracted_text == "hello world"
    assert updated.extracted_at is not None

    events = get_stream_events(db, stream_id=document.id)
    assert [e.event_type for e in events] == ["DocumentUploaded", "DocumentTextExtracted"]


def test_record_extraction_failure_marks_document_failed(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_minimal_pdf_bytes(),
    )

    updated = commands.record_extraction_failure(
        db, document_id=document.id, error="corrupt file"
    )

    assert updated.status == "failed"
    assert updated.error == "corrupt file"

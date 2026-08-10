import uuid
from datetime import date, timedelta
from io import BytesIO

import pytest
from celery.exceptions import Retry
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.llm_client import ExtractedFact, LLMExtractionError
from app.documents import commands, tasks as document_tasks
from app.documents.models import Document
from app.documents.tasks import process_document
from app.patients import commands as patient_commands
from app.profile.models import ProfileField


def _minimal_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _pdf_bytes_with_text(text: str) -> bytes:
    """Hand-built single-page PDF with a real content stream — pypdf's
    PdfWriter has no simple API for adding text, and this is the only way
    to exercise the fact-extraction path (which skips blank documents).
    """
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
    ]
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects.append(b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream")
    objects.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    out = b"%PDF-1.4\n"
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        out += ("%010d 00000 n \n" % offset).encode()
    out += (
        b"trailer\n<</Size " + str(len(objects) + 1).encode() + b"/Root 1 0 R>>\n"
        b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    )
    return out


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


def test_process_document_merges_extracted_facts_into_profile(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_pdf_bytes_with_text("Patient is non-weight-bearing for two weeks post-op."),
    )

    monkeypatch.setattr(
        document_tasks,
        "extract_facts",
        lambda text, schema: [
            ExtractedFact(
                field_name="active_restrictions",
                value="Non-weight-bearing for two weeks",
                confidence=0.92,
                source_quote="non-weight-bearing for two weeks post-op",
            )
        ],
    )

    process_document(str(document.id))

    verify_session = SessionLocal()
    try:
        refreshed = verify_session.get(Document, document.id)
        assert refreshed.status == "extracted"

        rows = list(
            verify_session.execute(
                select(ProfileField).where(ProfileField.patient_id == patient_id)
            ).scalars()
        )
        assert len(rows) == 1
        assert rows[0].field_name == "active_restrictions"
        assert rows[0].value == "Non-weight-bearing for two weeks"
        assert rows[0].source_document_id == document.id
    finally:
        verify_session.close()


def test_process_document_marks_failed_when_fact_extraction_fails(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_pdf_bytes_with_text("Patient reports mild anterior knee pain."),
    )

    def _raise(text: str, schema: list[str]) -> list[ExtractedFact]:
        raise LLMExtractionError("Gemini request failed")

    monkeypatch.setattr(document_tasks, "extract_facts", _raise)

    process_document(str(document.id))

    verify_session = SessionLocal()
    try:
        refreshed = verify_session.get(Document, document.id)
        assert refreshed.status == "failed"
        assert "Gemini request failed" in refreshed.error
    finally:
        verify_session.close()


def test_process_document_retries_transient_llm_failure_without_marking_failed(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_pdf_bytes_with_text("Patient reports mild anterior knee pain."),
    )

    def _raise(text: str, schema: list[str]) -> list[ExtractedFact]:
        raise LLMExtractionError("Gemini request failed: [Errno -5] No address associated with hostname")

    monkeypatch.setattr(document_tasks, "extract_facts", _raise)

    retry_calls = []

    def _fake_retry(exc=None, countdown=None, **kwargs):
        # Stands in for a real worker context, where retry() raises Retry
        # (rather than re-raising exc, as it does when called_directly).
        retry_calls.append((exc, countdown))
        raise Retry(exc=exc)

    monkeypatch.setattr(process_document, "retry", _fake_retry)

    with pytest.raises(Retry):
        process_document(str(document.id))

    assert len(retry_calls) == 1
    assert isinstance(retry_calls[0][0], LLMExtractionError)
    assert retry_calls[0][1] == document_tasks.RETRYABLE_COUNTDOWN_SECONDS

    verify_session = SessionLocal()
    try:
        refreshed = verify_session.get(Document, document.id)
        # A retry was scheduled, not a terminal failure — status/error
        # must be untouched so a later successful attempt isn't shadowed.
        assert refreshed.status == "processing"
        assert refreshed.error is None
    finally:
        verify_session.close()


def test_process_document_marks_failed_when_llm_retries_exhausted(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_pdf_bytes_with_text("Patient reports mild anterior knee pain."),
    )

    def _raise(text: str, schema: list[str]) -> list[ExtractedFact]:
        raise LLMExtractionError("Gemini request failed")

    monkeypatch.setattr(document_tasks, "extract_facts", _raise)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("retry() should not be attempted once max_retries is reached")

    monkeypatch.setattr(process_document, "retry", _fail_if_called)

    process_document.push_request(retries=process_document.max_retries)
    try:
        process_document(str(document.id))
    finally:
        process_document.pop_request()

    verify_session = SessionLocal()
    try:
        refreshed = verify_session.get(Document, document.id)
        assert refreshed.status == "failed"
        assert "Gemini request failed" in refreshed.error
    finally:
        verify_session.close()


def test_process_document_skips_rag_indexing_when_facts_staged(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_tasks.process_document, "delay", lambda *a, **kw: None)

    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_pdf_bytes_with_text("Patient reports mild anterior knee pain."),
    )

    monkeypatch.setattr(
        document_tasks,
        "extract_facts",
        lambda text, schema: [
            ExtractedFact(
                field_name="milestones",
                value="Uncertain milestone",
                confidence=0.3,
                source_quote="q1",
            )
        ],
    )
    index_calls: list[uuid.UUID] = []
    monkeypatch.setattr(
        document_tasks.rag_commands,
        "index_document_residual_text",
        lambda db, *, patient, document, text: index_calls.append(document.id),
    )

    process_document(str(document.id))

    assert index_calls == []
    verify_session = SessionLocal()
    try:
        refreshed = verify_session.get(Document, document.id)
        assert refreshed.status == "extracted"
    finally:
        verify_session.close()


def test_process_document_runs_rag_indexing_when_no_facts_staged(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_tasks.process_document, "delay", lambda *a, **kw: None)

    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_pdf_bytes_with_text("Patient reports mild anterior knee pain."),
    )

    monkeypatch.setattr(
        document_tasks,
        "extract_facts",
        lambda text, schema: [
            ExtractedFact(
                field_name="milestones",
                value="Full extension achieved",
                confidence=0.9,
                source_quote="q1",
            )
        ],
    )
    index_calls: list[uuid.UUID] = []
    monkeypatch.setattr(
        document_tasks.rag_commands,
        "index_document_residual_text",
        lambda db, *, patient, document, text: index_calls.append(document.id),
    )

    process_document(str(document.id))

    assert index_calls == [document.id]


def test_run_deferred_rag_indexing_indexes_document_text(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_tasks.process_document, "delay", lambda *a, **kw: None)

    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_pdf_bytes_with_text("Patient reports mild anterior knee pain."),
    )
    commands.record_extraction_result(
        db, document_id=document.id, extracted_text="Patient reports mild anterior knee pain."
    )

    index_calls: list[str] = []
    monkeypatch.setattr(
        document_tasks.rag_commands,
        "index_document_residual_text",
        lambda db, *, patient, document, text: index_calls.append(text),
    )

    document_tasks.run_deferred_rag_indexing(str(document.id))

    assert index_calls == ["Patient reports mild anterior knee pain."]


def test_process_document_still_extracted_when_rag_indexing_fails(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # upload_document() also dispatches process_document via Celery .delay()
    # to the real worker container; suppress that so this test's synchronous
    # call is the only thing processing this document (avoids a race with
    # the live worker's own, unpatched run of the same document).
    monkeypatch.setattr(document_tasks.process_document, "delay", lambda *a, **kw: None)

    therapist_id, patient_id = _make_patient(db)
    document = commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="mri-report.pdf",
        content_type="application/pdf",
        file_bytes=_pdf_bytes_with_text("Patient reports mild anterior knee pain."),
    )

    def _raise(db, *, patient, document, text):
        raise RuntimeError("embedding API hiccup")

    monkeypatch.setattr(document_tasks.rag_commands, "index_document_residual_text", _raise)

    process_document(str(document.id))

    verify_session = SessionLocal()
    try:
        refreshed = verify_session.get(Document, document.id)
        assert refreshed.status == "extracted"
        assert refreshed.extracted_text is not None
    finally:
        verify_session.close()

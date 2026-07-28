import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.core.config import settings
from app.core.llm_client import ExtractedFact
from app.documents import commands as document_commands
from app.documents.models import Document
from app.patients import commands as patient_commands
from app.patients.models import Patient
from app.profile.commands import merge_extracted_facts
from app.timeline.models import (
    ENTRY_TYPE_DOCUMENT_EXTRACTED,
    ENTRY_TYPE_MILESTONE,
    ENTRY_TYPE_PHASE_ADVANCE,
    TimelineEntry,
)

FIXED_SURGERY_DATE = date.today() + timedelta(days=14)


def _minimal_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_patient_and_document(db: Session) -> tuple[Patient, Document]:
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
        surgery_date=FIXED_SURGERY_DATE,
    )
    document = document_commands.upload_document(
        db,
        patient_id=patient.id,
        therapist_id=therapist.id,
        filename="note.pdf",
        content_type="application/pdf",
        file_bytes=_minimal_pdf_bytes(),
    )
    return patient, document


def _entries_for(db: Session, *, patient_id: uuid.UUID) -> list[TimelineEntry]:
    return list(
        db.execute(
            select(TimelineEntry)
            .where(TimelineEntry.patient_id == patient_id)
            .order_by(TimelineEntry.occurred_at)
        ).scalars()
    )


def test_phase_advance_projects_a_timeline_entry(db: Session) -> None:
    patient, _ = _make_patient_and_document(db)

    patient_commands.advance_phase(
        db,
        patient_id=patient.id,
        therapist_id=patient.therapist_id,
        target_phase="phase_1_protection",
        note="cleared for phase 1",
    )

    entries = _entries_for(db, patient_id=patient.id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == ENTRY_TYPE_PHASE_ADVANCE
    assert entry.therapist_id == patient.therapist_id
    assert entry.detail == {
        "from_phase": "pre_op",
        "to_phase": "phase_1_protection",
        "note": "cleared for phase 1",
    }


def test_document_extraction_projects_a_timeline_entry(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    document_commands.record_extraction_result(
        db, document_id=document.id, extracted_text="hello world"
    )

    entries = _entries_for(db, patient_id=patient.id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == ENTRY_TYPE_DOCUMENT_EXTRACTED
    assert entry.therapist_id == document.therapist_id
    assert entry.detail == {"filename": "note.pdf", "document_id": str(document.id)}


def test_document_extraction_failure_projects_no_timeline_entry(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    document_commands.record_extraction_failure(
        db, document_id=document.id, error="corrupt file"
    )

    assert _entries_for(db, patient_id=patient.id) == []


def test_milestone_fact_projects_a_timeline_entry(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="milestones",
                value="Full extension achieved",
                confidence=0.9,
                source_quote="q1",
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    entries = _entries_for(db, patient_id=patient.id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == ENTRY_TYPE_MILESTONE
    assert entry.detail == {
        "value": "Full extension achieved",
        "confidence": 0.9,
        "source_quote": "q1",
        "source_document_id": str(document.id),
    }


def test_non_milestone_field_projects_no_timeline_entry(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="active_restrictions",
                value="No pivoting",
                confidence=0.9,
                source_quote="q1",
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    assert _entries_for(db, patient_id=patient.id) == []


def test_mixed_field_batch_only_projects_the_milestone_facts(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="milestones",
                value="Full extension achieved",
                confidence=0.9,
                source_quote="q1",
            ),
            ExtractedFact(
                field_name="active_restrictions",
                value="No pivoting",
                confidence=0.9,
                source_quote="q2",
            ),
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    entries = _entries_for(db, patient_id=patient.id)
    assert len(entries) == 1
    assert entries[0].entry_type == ENTRY_TYPE_MILESTONE
    assert entries[0].detail["value"] == "Full extension achieved"

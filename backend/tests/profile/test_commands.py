import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

import pytest
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
from app.profile.commands import (
    NotAContradiction,
    ProfileFieldNotFound,
    acknowledge_contradiction,
    merge_extracted_facts,
)
from app.profile.models import ProfileField

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


def _current_rows(db: Session, *, patient_id: uuid.UUID, field_name: str) -> list[ProfileField]:
    return list(
        db.execute(
            select(ProfileField).where(
                ProfileField.patient_id == patient_id,
                ProfileField.field_name == field_name,
                ProfileField.superseded_at.is_(None),
            )
        ).scalars()
    )


def test_overwrite_strategy_batches_facts_from_one_call_together(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    facts = [
        ExtractedFact(
            field_name="active_restrictions", value="No pivoting", confidence=0.9, source_quote="q1"
        ),
        ExtractedFact(
            field_name="active_restrictions",
            value="Brace required",
            confidence=0.8,
            source_quote="q2",
        ),
    ]
    merge_extracted_facts(
        db, patient=patient, document=document, facts=facts, extracted_at=datetime.now(timezone.utc)
    )

    current = _current_rows(db, patient_id=patient.id, field_name="active_restrictions")
    assert {row.value for row in current} == {"No pivoting", "Brace required"}
    assert all(row.confidence is not None for row in current)


def test_overwrite_strategy_supersedes_prior_batch_wholesale(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="active_restrictions", value="No pivoting", confidence=0.9, source_quote="q1"
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )
    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="active_restrictions",
                value="Cleared for light jogging",
                confidence=0.85,
                source_quote="q3",
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    current = _current_rows(db, patient_id=patient.id, field_name="active_restrictions")
    assert [row.value for row in current] == ["Cleared for light jogging"]

    all_rows = list(
        db.execute(
            select(ProfileField).where(
                ProfileField.patient_id == patient.id, ProfileField.field_name == "active_restrictions"
            )
        ).scalars()
    )
    assert len(all_rows) == 2
    superseded = [row for row in all_rows if row.superseded_at is not None]
    assert len(superseded) == 1
    assert superseded[0].value == "No pivoting"


def test_append_only_strategy_accumulates_without_superseding(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="milestones", value="Full extension achieved", confidence=0.9, source_quote="q1"
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )
    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="milestones", value="Cleared for stationary bike", confidence=0.9, source_quote="q2"
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    current = _current_rows(db, patient_id=patient.id, field_name="milestones")
    assert {row.value for row in current} == {"Full extension achieved", "Cleared for stationary bike"}


def test_append_only_strategy_dedupes_identical_value(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    for _ in range(2):
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

    current = _current_rows(db, patient_id=patient.id, field_name="milestones")
    assert len(current) == 1


def test_injury_freetext_phrasing_of_same_diagnosis_is_not_a_contradiction(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    written = merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="injury",
                value="Right knee ACL reconstruction",
                confidence=0.9,
                source_quote="q1",
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    assert len(written) == 1
    assert written[0].is_contradiction is False


def test_injury_genuinely_different_diagnosis_is_a_contradiction(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    written = merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="injury", value="Medial meniscus tear", confidence=0.9, source_quote="q1"
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    assert len(written) == 1
    assert written[0].is_contradiction is True


def test_immutable_field_matching_baseline_is_not_a_contradiction(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    written = merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="surgery_date",
                value=FIXED_SURGERY_DATE.isoformat(),
                confidence=0.95,
                source_quote="q1",
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    assert len(written) == 1
    assert written[0].is_contradiction is False


def test_immutable_field_conflicting_with_baseline_is_flagged_and_not_applied(db: Session) -> None:
    patient, document = _make_patient_and_document(db)
    conflicting_date = (FIXED_SURGERY_DATE + timedelta(days=5)).isoformat()

    written = merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="surgery_date", value=conflicting_date, confidence=0.7, source_quote="q1"
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    assert len(written) == 1
    assert written[0].is_contradiction is True
    # The authoritative admin field is untouched — contradictions are surfaced, never silently applied.
    assert patient.surgery_date == FIXED_SURGERY_DATE


def test_acknowledge_contradiction_sets_acknowledged_at(db: Session) -> None:
    patient, document = _make_patient_and_document(db)
    written = merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="injury", value="Medial meniscus tear", confidence=0.9, source_quote="q1"
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )
    field = written[0]
    assert field.acknowledged_at is None

    acknowledged = acknowledge_contradiction(
        db, patient_id=patient.id, therapist_id=patient.therapist_id, field_id=field.id
    )

    assert acknowledged.acknowledged_at is not None


def test_acknowledge_contradiction_is_idempotent(db: Session) -> None:
    patient, document = _make_patient_and_document(db)
    written = merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="injury", value="Medial meniscus tear", confidence=0.9, source_quote="q1"
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )
    field_id = written[0].id

    first = acknowledge_contradiction(
        db, patient_id=patient.id, therapist_id=patient.therapist_id, field_id=field_id
    )
    second = acknowledge_contradiction(
        db, patient_id=patient.id, therapist_id=patient.therapist_id, field_id=field_id
    )

    assert first.acknowledged_at == second.acknowledged_at


def test_acknowledge_contradiction_rejects_non_contradiction_field(db: Session) -> None:
    patient, document = _make_patient_and_document(db)
    written = merge_extracted_facts(
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

    with pytest.raises(NotAContradiction):
        acknowledge_contradiction(
            db, patient_id=patient.id, therapist_id=patient.therapist_id, field_id=written[0].id
        )


def test_acknowledge_contradiction_rejects_unknown_field(db: Session) -> None:
    patient, _document = _make_patient_and_document(db)

    with pytest.raises(ProfileFieldNotFound):
        acknowledge_contradiction(
            db, patient_id=patient.id, therapist_id=patient.therapist_id, field_id=uuid.uuid4()
        )


def test_unrecognized_field_name_is_silently_ignored(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    written = merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="current_phase", value="phase_5_return_to_sport", confidence=0.9, source_quote="q1"
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    assert written == []

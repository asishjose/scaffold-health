import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

import pytest
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.core.config import settings
from app.core.llm_client import ExtractedFact
from app.documents import commands as document_commands
from app.documents.models import Document
from app.patients import commands as patient_commands
from app.patients.models import Patient
from app.profile.commands import merge_extracted_facts
from app.rag import commands as rag_commands
from app.rag.events import SCOPE_CLINICAL_GUIDELINES, SCOPE_PATIENT_NOTES
from app.rag.models import RagChunk

FIXED_SURGERY_DATE = date.today() + timedelta(days=14)
FAKE_EMBEDDING = [0.1] * 768


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


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag_commands, "embed_text", lambda text, **kw: list(FAKE_EMBEDDING))


def test_index_document_residual_text_writes_scoped_chunks(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    text = (
        "The patient continues to make steady progress with range of motion "
        "and reports minimal pain during daily activities, with full extension "
        "now consistently achieved during therapy sessions and no new concerns "
        "raised at today's visit."
    )

    rows = rag_commands.index_document_residual_text(db, patient=patient, document=document, text=text)

    assert len(rows) >= 1
    for row in rows:
        assert row.scope == SCOPE_PATIENT_NOTES
        assert row.patient_id == patient.id
        assert row.therapist_id == patient.therapist_id
        assert row.source_type == "document"
        assert row.source_document_id == document.id
        assert row.embedding == FAKE_EMBEDDING

    persisted = db.query(RagChunk).filter(RagChunk.patient_id == patient.id).all()
    assert len(persisted) == len(rows)


def test_chunk_restating_a_known_profile_value_is_rejected(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="active_restrictions",
                value="No pivoting or cutting movements for six weeks post-op",
                confidence=0.9,
                source_quote="q1",
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    # This document's residual text just restates the known structured
    # value above almost verbatim, padded to clear the min-chunk-length
    # floor, and should be rejected by the allowlist check rather than
    # embedded and indexed.
    restating_text = "No pivoting or cutting movements for six weeks post-op."

    rows = rag_commands.index_document_residual_text(
        db, patient=patient, document=document, text=restating_text
    )

    assert rows == []
    assert db.query(RagChunk).filter(RagChunk.patient_id == patient.id).count() == 0


def test_novel_content_in_a_separate_chunk_survives_a_sibling_rejection(db: Session) -> None:
    # A restated known value shares a chunk with padding and gets rejected
    # wholesale (chunk-granularity filtering, Decision D) — but genuinely
    # novel content that lands in a *different* chunk (once the document is
    # long enough to split) must still be indexed.
    patient, document = _make_patient_and_document(db)

    known_value = "No pivoting or cutting movements for six weeks post-op"
    merge_extracted_facts(
        db,
        patient=patient,
        document=document,
        facts=[
            ExtractedFact(
                field_name="active_restrictions",
                value=known_value,
                confidence=0.9,
                source_quote="q1",
            )
        ],
        extracted_at=datetime.now(timezone.utc),
    )

    novel_sentences = " ".join(
        f"This is unrelated follow-up note number {i} describing steady, "
        f"uneventful progress with no new complaints raised at this visit."
        for i in range(6)
    )
    text = f"{known_value}. {novel_sentences}"

    rows = rag_commands.index_document_residual_text(db, patient=patient, document=document, text=text)

    assert len(rows) >= 1
    assert all(known_value.lower() not in row.chunk_text.lower() for row in rows)
    joined = " ".join(row.chunk_text for row in rows)
    assert "note number 5" in joined


def test_empty_chunks_writes_no_event_or_rows(db: Session) -> None:
    patient, document = _make_patient_and_document(db)

    rows = rag_commands.index_document_residual_text(db, patient=patient, document=document, text="")

    assert rows == []
    assert db.query(RagChunk).filter(RagChunk.patient_id == patient.id).count() == 0


def test_seed_shared_corpus_writes_null_patient_scoped_rows(db: Session) -> None:
    text = (
        "Ice your knee for fifteen to twenty minutes at a time, several "
        "times a day, to help manage swelling and discomfort during early recovery."
    )

    rows = rag_commands.seed_shared_corpus(
        db,
        scope=SCOPE_CLINICAL_GUIDELINES,
        source_type="guideline_seed",
        label="icing.txt",
        text=text,
    )

    assert len(rows) >= 1
    for row in rows:
        assert row.scope == SCOPE_CLINICAL_GUIDELINES
        assert row.patient_id is None
        assert row.therapist_id is None
        assert row.source_label == "icing.txt"


def test_seed_shared_corpus_is_idempotent_per_label(db: Session) -> None:
    text = "Keep your leg elevated above heart level while resting to reduce swelling."

    first = rag_commands.seed_shared_corpus(
        db, scope=SCOPE_CLINICAL_GUIDELINES, source_type="guideline_seed", label="elevate.txt", text=text
    )
    second = rag_commands.seed_shared_corpus(
        db, scope=SCOPE_CLINICAL_GUIDELINES, source_type="guideline_seed", label="elevate.txt", text=text
    )

    assert [r.id for r in first] == [r.id for r in second]
    assert db.query(RagChunk).filter(RagChunk.source_label == "elevate.txt").count() == len(first)

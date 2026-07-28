import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm_client import ExtractedFact
from app.core.security import TokenType, create_access_token, decode_token
from app.documents import commands as document_commands
from app.main import app
from app.patients.models import Patient
from app.profile.commands import merge_extracted_facts

client = TestClient(app)


def _minimal_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _signup_and_login_therapist() -> tuple[str, uuid.UUID]:
    email = f"therapist-{uuid.uuid4()}@example.com"
    client.post(
        "/auth/signup",
        json={
            "name": "Dana Therapist",
            "email": email,
            "password": "a-strong-password",
            "registration_code": settings.clinic_registration_code,
        },
    )
    login = client.post(
        "/auth/login", json={"email": email, "password": "a-strong-password"}
    ).json()
    token = login["access_token"]
    therapist_id = uuid.UUID(decode_token(token, expected_type=TokenType.ACCESS)["sub"])
    return token, therapist_id


def _create_patient(token: str) -> dict:
    payload = {
        "name": "Pat Patient",
        "date_of_birth": "1990-01-01",
        "contact_email": f"patient-{uuid.uuid4()}@example.com",
        "surgery_date": (date.today() + timedelta(days=14)).isoformat(),
    }
    return client.post("/patients", json=payload, headers=_auth_headers(token)).json()


def _seed_full_timeline(db: Session, *, token: str, therapist_id: uuid.UUID, created: dict) -> str:
    """Drives one entry of each type for a freshly created patient: a phase
    advance via the real HTTP endpoint, and a document extraction + a
    milestone fact via direct command calls (both normally happen
    asynchronously via Celery/Gemini, so — matching the existing
    tests/documents and tests/profile convention — they're driven directly
    against the command layer instead of waiting on a live LLM call).
    """
    patient_id = uuid.UUID(created["id"])

    client.post(
        f"/patients/{patient_id}/phase",
        json={"target_phase": "phase_1_protection", "note": "cleared for phase 1"},
        headers=_auth_headers(token),
    )

    document = document_commands.upload_document(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        filename="note.pdf",
        content_type="application/pdf",
        file_bytes=_minimal_pdf_bytes(),
    )
    document_commands.record_extraction_result(
        db, document_id=document.id, extracted_text="hello world"
    )

    patient = db.get(Patient, patient_id)
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

    return str(patient_id)


def test_therapist_sees_full_timeline_with_provenance(db: Session) -> None:
    token, therapist_id = _signup_and_login_therapist()
    created = _create_patient(token)
    patient_id = _seed_full_timeline(db, token=token, therapist_id=therapist_id, created=created)

    response = client.get(f"/patients/{patient_id}/timeline", headers=_auth_headers(token))

    assert response.status_code == 200, response.text
    entries = response.json()
    assert [e["entry_type"] for e in entries] == [
        "phase_advance",
        "document_extracted",
        "milestone",
    ]

    milestone = next(e for e in entries if e["entry_type"] == "milestone")
    assert milestone["value"] == "Full extension achieved"
    assert milestone["confidence"] == 0.9
    assert milestone["source_quote"] == "q1"
    assert milestone["source_document_id"] is not None


def test_patient_sees_reduced_timeline_without_provenance(db: Session) -> None:
    token, therapist_id = _signup_and_login_therapist()
    created = _create_patient(token)
    patient_id = _seed_full_timeline(db, token=token, therapist_id=therapist_id, created=created)

    accept = client.post(
        f"/auth/invite/{created['invite_token']}", json={"password": "patient-password"}
    )
    patient_email = accept.json()["email"]
    login = client.post(
        "/auth/login", json={"email": patient_email, "password": "patient-password"}
    ).json()
    patient_token = login["access_token"]

    response = client.get(
        f"/patients/{patient_id}/timeline", headers=_auth_headers(patient_token)
    )

    assert response.status_code == 200, response.text
    entries = response.json()
    assert [e["entry_type"] for e in entries] == [
        "phase_advance",
        "document_extracted",
        "milestone",
    ]

    milestone = next(e for e in entries if e["entry_type"] == "milestone")
    assert milestone["value"] == "Full extension achieved"
    assert "confidence" not in milestone
    assert "source_quote" not in milestone
    assert "source_document_id" not in milestone

    phase_advance = next(e for e in entries if e["entry_type"] == "phase_advance")
    assert phase_advance["to_phase"] == "phase_1_protection"


def test_get_timeline_rejects_non_owning_therapist() -> None:
    token_a, _ = _signup_and_login_therapist()
    token_b, _ = _signup_and_login_therapist()
    created = _create_patient(token_a)

    response = client.get(
        f"/patients/{created['id']}/timeline", headers=_auth_headers(token_b)
    )

    assert response.status_code == 404


def test_get_timeline_rejects_other_patient() -> None:
    token, _ = _signup_and_login_therapist()
    created = _create_patient(token)
    other_patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.get(
        f"/patients/{created['id']}/timeline", headers=_auth_headers(other_patient_token)
    )

    assert response.status_code == 403


def test_get_timeline_rejects_unauthenticated() -> None:
    response = client.get(f"/patients/{uuid.uuid4()}/timeline")

    assert response.status_code == 401

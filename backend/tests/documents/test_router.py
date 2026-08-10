import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.patients.models import Patient
from app.profile.events import PENDING_STATUS_PENDING, PENDING_STATUS_REJECTED
from app.profile.models import PendingProfileFact

client = TestClient(app)


def _minimal_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _signup_and_login_therapist() -> str:
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
    return login["access_token"]


def _create_patient(token: str) -> str:
    payload = {
        "name": "Pat Patient",
        "date_of_birth": "1990-01-01",
        "contact_email": f"patient-{uuid.uuid4()}@example.com",
        "surgery_date": (date.today() + timedelta(days=14)).isoformat(),
    }
    response = client.post("/patients", json=payload, headers=_auth_headers(token))
    return response.json()["id"]


def test_upload_document_as_owning_therapist() -> None:
    token = _signup_and_login_therapist()
    patient_id = _create_patient(token)

    response = client.post(
        f"/patients/{patient_id}/documents",
        files={"file": ("mri-report.pdf", _minimal_pdf_bytes(), "application/pdf")},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "mri-report.pdf"
    assert body["status"] == "processing"


def test_upload_document_rejects_non_pdf() -> None:
    token = _signup_and_login_therapist()
    patient_id = _create_patient(token)

    response = client.post(
        f"/patients/{patient_id}/documents",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        headers=_auth_headers(token),
    )

    assert response.status_code == 400


def test_upload_document_rejects_non_owning_therapist() -> None:
    token_a = _signup_and_login_therapist()
    token_b = _signup_and_login_therapist()
    patient_id = _create_patient(token_a)

    response = client.post(
        f"/patients/{patient_id}/documents",
        files={"file": ("mri-report.pdf", _minimal_pdf_bytes(), "application/pdf")},
        headers=_auth_headers(token_b),
    )

    assert response.status_code == 404


def test_upload_document_rejects_patient_role() -> None:
    token = _signup_and_login_therapist()
    patient_id = _create_patient(token)
    patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.post(
        f"/patients/{patient_id}/documents",
        files={"file": ("mri-report.pdf", _minimal_pdf_bytes(), "application/pdf")},
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 403


def test_list_documents_scoped_to_owning_therapist() -> None:
    token_a = _signup_and_login_therapist()
    token_b = _signup_and_login_therapist()
    patient_id = _create_patient(token_a)
    client.post(
        f"/patients/{patient_id}/documents",
        files={"file": ("mri-report.pdf", _minimal_pdf_bytes(), "application/pdf")},
        headers=_auth_headers(token_a),
    )

    list_a = client.get(f"/patients/{patient_id}/documents", headers=_auth_headers(token_a))
    list_b = client.get(f"/patients/{patient_id}/documents", headers=_auth_headers(token_b))

    assert list_a.status_code == 200
    assert len(list_a.json()) == 1
    assert list_b.status_code == 404


def test_list_documents_reflects_has_pending_facts(db: Session) -> None:
    token = _signup_and_login_therapist()
    patient_id = _create_patient(token)
    upload = client.post(
        f"/patients/{patient_id}/documents",
        files={"file": ("mri-report.pdf", _minimal_pdf_bytes(), "application/pdf")},
        headers=_auth_headers(token),
    )
    document_id = upload.json()["id"]
    therapist_id = db.get(Patient, uuid.UUID(patient_id)).therapist_id

    before = client.get(f"/patients/{patient_id}/documents", headers=_auth_headers(token))
    assert before.json()[0]["has_pending_facts"] is False

    pending = PendingProfileFact(
        id=uuid.uuid4(),
        patient_id=uuid.UUID(patient_id),
        therapist_id=therapist_id,
        source_document_id=uuid.UUID(document_id),
        field_name="milestones",
        value="Uncertain milestone",
        confidence=0.3,
        source_quote="q1",
        is_contradiction=False,
        is_low_confidence=True,
        extractor_version="test",
        extracted_at=datetime.now(timezone.utc),
        status=PENDING_STATUS_PENDING,
    )
    db.add(pending)
    db.commit()

    during = client.get(f"/patients/{patient_id}/documents", headers=_auth_headers(token))
    assert during.json()[0]["has_pending_facts"] is True

    pending.status = PENDING_STATUS_REJECTED
    db.commit()

    after = client.get(f"/patients/{patient_id}/documents", headers=_auth_headers(token))
    assert after.json()[0]["has_pending_facts"] is False

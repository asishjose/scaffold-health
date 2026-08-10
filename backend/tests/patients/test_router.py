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


def _signup_and_login_therapist() -> tuple[str, str]:
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
    return login["access_token"], email


def _intake_payload() -> dict:
    return {
        "name": "Pat Patient",
        "date_of_birth": "1990-01-01",
        "contact_email": f"patient-{uuid.uuid4()}@example.com",
        "surgery_date": (date.today() + timedelta(days=14)).isoformat(),
    }


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _therapist_id_from_token(token: str) -> uuid.UUID:
    return uuid.UUID(decode_token(token, expected_type=TokenType.ACCESS)["sub"])


def test_create_patient_as_therapist() -> None:
    token, _ = _signup_and_login_therapist()

    response = client.post("/patients", json=_intake_payload(), headers=_auth_headers(token))

    assert response.status_code == 201, response.text
    body = response.json()
    assert "invite_token" in body
    assert "invite_expires_at" in body


def test_create_patient_rejects_patient_role() -> None:
    patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(patient_token)
    )

    assert response.status_code == 403


def test_caseload_is_scoped_to_therapist() -> None:
    token_a, _ = _signup_and_login_therapist()
    token_b, _ = _signup_and_login_therapist()

    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token_a)
    ).json()

    list_a = client.get("/patients", headers=_auth_headers(token_a)).json()
    list_b = client.get("/patients", headers=_auth_headers(token_b)).json()

    assert any(p["id"] == created["id"] for p in list_a)
    assert not any(p["id"] == created["id"] for p in list_b)


def test_get_patient_detail_as_owning_therapist() -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()

    response = client.get(f"/patients/{created['id']}", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["contact_email"]
    assert "therapist_id" in body


def test_get_patient_detail_rejects_non_owning_therapist() -> None:
    token_a, _ = _signup_and_login_therapist()
    token_b, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token_a)
    ).json()

    response = client.get(f"/patients/{created['id']}", headers=_auth_headers(token_b))

    assert response.status_code == 404


def test_invite_preview_and_acceptance_flow() -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    invite_token = created["invite_token"]

    preview = client.get(f"/auth/invite/{invite_token}")
    assert preview.status_code == 200

    accept = client.post(f"/auth/invite/{invite_token}", json={"password": "patient-password"})
    assert accept.status_code == 200
    patient_id = accept.json()["id"]
    patient_email = accept.json()["email"]

    reused = client.post(f"/auth/invite/{invite_token}", json={"password": "another-password"})
    assert reused.status_code == 409

    login = client.post(
        "/auth/login", json={"email": patient_email, "password": "patient-password"}
    )
    assert login.status_code == 200
    patient_token = login.json()["access_token"]

    own_detail = client.get(f"/patients/{patient_id}", headers=_auth_headers(patient_token))
    assert own_detail.status_code == 200
    body = own_detail.json()
    assert body["current_phase"] == "pre_op"
    assert "contact_email" not in body
    assert "therapist_id" not in body


def test_get_patient_detail_rejects_other_patient() -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    other_patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.get(
        f"/patients/{created['id']}", headers=_auth_headers(other_patient_token)
    )

    assert response.status_code == 403


def test_invite_preview_unknown_token_returns_404() -> None:
    response = client.get("/auth/invite/not-a-real-token")

    assert response.status_code == 404


def test_advance_phase_as_owning_therapist() -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()

    response = client.post(
        f"/patients/{created['id']}/phase",
        json={"target_phase": "phase_1_protection", "note": "cleared for phase 1"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["current_phase"] == "phase_1_protection"


def test_advance_phase_rejects_skipping_ahead() -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()

    response = client.post(
        f"/patients/{created['id']}/phase",
        json={"target_phase": "phase_2_early_strength", "note": None},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_advance_phase_rejects_patient_role() -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.post(
        f"/patients/{created['id']}/phase",
        json={"target_phase": "phase_1_protection", "note": None},
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 403


def test_advance_phase_rejects_non_owning_therapist() -> None:
    token_a, _ = _signup_and_login_therapist()
    token_b, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token_a)
    ).json()

    response = client.post(
        f"/patients/{created['id']}/phase",
        json={"target_phase": "phase_1_protection", "note": None},
        headers=_auth_headers(token_b),
    )

    assert response.status_code == 404


def _seed_pending_fact(db: Session, *, token: str, patient_id: str) -> str:
    """Pending facts are only ever produced by the extraction pipeline
    (normally driven by a live Groq/Gemini call), so — matching the
    tests/profile convention — this drives the merge command directly
    instead of standing up a real extraction.
    """
    therapist_id = _therapist_id_from_token(token)
    patient = db.get(Patient, uuid.UUID(patient_id))
    document = document_commands.upload_document(
        db,
        patient_id=patient.id,
        therapist_id=therapist_id,
        filename="note.pdf",
        content_type="application/pdf",
        file_bytes=_minimal_pdf_bytes(),
    )
    result = merge_extracted_facts(
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
    assert therapist_id == patient.therapist_id
    assert result.merged == []
    return str(result.staged[0].id)


def test_get_patient_needs_review_reflects_pending_facts(db: Session) -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    fact_id = _seed_pending_fact(db, token=token, patient_id=created["id"])

    before = client.get(f"/patients/{created['id']}", headers=_auth_headers(token)).json()
    assert "Pending extraction" in before["needs_review"]

    reject = client.post(
        f"/patients/{created['id']}/pending-facts/{fact_id}/reject",
        headers=_auth_headers(token),
    )
    assert reject.status_code == 200, reject.text

    after = client.get(f"/patients/{created['id']}", headers=_auth_headers(token)).json()
    assert "Pending extraction" not in after["needs_review"]


def test_list_pending_facts_scoped_to_owning_therapist(db: Session) -> None:
    token_a, _ = _signup_and_login_therapist()
    token_b, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token_a)
    ).json()
    _seed_pending_fact(db, token=token_a, patient_id=created["id"])

    list_a = client.get(f"/patients/{created['id']}/pending-facts", headers=_auth_headers(token_a))
    list_b = client.get(f"/patients/{created['id']}/pending-facts", headers=_auth_headers(token_b))

    assert list_a.status_code == 200
    assert len(list_a.json()) == 1
    assert list_a.json()[0]["field_name"] == "injury"
    assert list_b.status_code == 404


def test_approve_pending_fact_as_owning_therapist(db: Session) -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    fact_id = _seed_pending_fact(db, token=token, patient_id=created["id"])

    response = client.post(
        f"/patients/{created['id']}/pending-facts/{fact_id}/approve",
        json={"value": None},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    assert body["resolved_value"] == "Medial meniscus tear"
    assert body["resulting_profile_field_id"] is not None


def test_approve_pending_fact_with_edited_value(db: Session) -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    fact_id = _seed_pending_fact(db, token=token, patient_id=created["id"])

    response = client.post(
        f"/patients/{created['id']}/pending-facts/{fact_id}/approve",
        json={"value": "ACL reconstruction (corrected)"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["resolved_value"] == "ACL reconstruction (corrected)"


def test_reject_pending_fact_as_owning_therapist(db: Session) -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    fact_id = _seed_pending_fact(db, token=token, patient_id=created["id"])

    response = client.post(
        f"/patients/{created['id']}/pending-facts/{fact_id}/reject",
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"


def test_approve_pending_fact_rejects_already_resolved(db: Session) -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    fact_id = _seed_pending_fact(db, token=token, patient_id=created["id"])
    client.post(
        f"/patients/{created['id']}/pending-facts/{fact_id}/reject", headers=_auth_headers(token)
    )

    response = client.post(
        f"/patients/{created['id']}/pending-facts/{fact_id}/approve",
        json={"value": None},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_approve_pending_fact_rejects_unknown_fact() -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()

    response = client.post(
        f"/patients/{created['id']}/pending-facts/{uuid.uuid4()}/approve",
        json={"value": None},
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def test_approve_pending_fact_rejects_non_owning_therapist(db: Session) -> None:
    token_a, _ = _signup_and_login_therapist()
    token_b, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token_a)
    ).json()
    fact_id = _seed_pending_fact(db, token=token_a, patient_id=created["id"])

    response = client.post(
        f"/patients/{created['id']}/pending-facts/{fact_id}/approve",
        json={"value": None},
        headers=_auth_headers(token_b),
    )

    assert response.status_code == 404


def test_approve_pending_fact_rejects_patient_role() -> None:
    token, _ = _signup_and_login_therapist()
    created = client.post(
        "/patients", json=_intake_payload(), headers=_auth_headers(token)
    ).json()
    patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.post(
        f"/patients/{created['id']}/pending-facts/{uuid.uuid4()}/approve",
        json={"value": None},
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 403

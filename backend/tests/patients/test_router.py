import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


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

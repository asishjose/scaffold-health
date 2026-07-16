import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


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


def _create_and_activate_patient(therapist_token: str) -> tuple[str, str]:
    patient_email = f"patient-{uuid.uuid4()}@example.com"
    created = client.post(
        "/patients",
        json={
            "name": "Pat Patient",
            "date_of_birth": "1990-01-01",
            "contact_email": patient_email,
            "surgery_date": (date.today() + timedelta(days=14)).isoformat(),
        },
        headers=_auth_headers(therapist_token),
    ).json()

    client.post(f"/auth/invite/{created['invite_token']}", json={"password": "patient-password"})
    login = client.post(
        "/auth/login", json={"email": patient_email, "password": "patient-password"}
    ).json()
    return created["id"], login["access_token"]


def test_submit_checkin_as_owning_patient() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)

    response = client.post(
        f"/patients/{patient_id}/checkins",
        json={"pain_level": 6, "note": "sore after PT"},
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["pain_level"] == 6
    assert body["note"] == "sore after PT"


def test_submit_checkin_rejects_out_of_range_pain_level() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)

    response = client.post(
        f"/patients/{patient_id}/checkins",
        json={"pain_level": 11, "note": None},
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 422


def test_submit_checkin_rejects_therapist_role() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, _ = _create_and_activate_patient(therapist_token)

    response = client.post(
        f"/patients/{patient_id}/checkins",
        json={"pain_level": 5, "note": None},
        headers=_auth_headers(therapist_token),
    )

    assert response.status_code == 403


def test_submit_checkin_rejects_other_patient() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, _ = _create_and_activate_patient(therapist_token)
    other_patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.post(
        f"/patients/{patient_id}/checkins",
        json={"pain_level": 5, "note": None},
        headers=_auth_headers(other_patient_token),
    )

    assert response.status_code == 403


def test_checkin_appears_in_therapist_patient_detail_pain_history() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)
    client.post(
        f"/patients/{patient_id}/checkins",
        json={"pain_level": 7, "note": "flare-up"},
        headers=_auth_headers(patient_token),
    )

    detail = client.get(f"/patients/{patient_id}", headers=_auth_headers(therapist_token))

    assert detail.status_code == 200
    pain_history = detail.json()["pain_history"]
    assert len(pain_history) == 1
    assert pain_history[0]["pain_level"] == 7
    assert pain_history[0]["note"] == "flare-up"

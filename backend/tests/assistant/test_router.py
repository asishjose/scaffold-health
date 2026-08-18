import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.assistant import commands as assistant_commands
from app.core.config import settings
from app.core.llm_client import AssistantAnswer
from app.core.security import create_access_token
from app.main import app

client = TestClient(app)

FAKE_EMBEDDING = [0.1] * 768


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


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assistant_commands, "embed_text", lambda text, **kw: list(FAKE_EMBEDDING))
    monkeypatch.setattr(
        assistant_commands,
        "answer_patient_question",
        lambda **kwargs: AssistantAnswer(answer="General answer.", redirect=False),
    )


def test_ask_assistant_as_owning_patient() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)

    response = client.post(
        f"/patients/{patient_id}/assistant",
        json={"question": "How do I use crutches?"},
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["patient_id"] == patient_id
    assert body["answer"] == "General answer."
    assert body["redirected"] is False


def test_ask_assistant_redirects_symptom_question_end_to_end() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)

    response = client.post(
        f"/patients/{patient_id}/assistant",
        json={"question": "My incision is red and draining, is that normal?"},
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["redirected"] is True
    assert "contact your clinic" in body["answer"]


def test_ask_assistant_rejects_therapist_role() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, _ = _create_and_activate_patient(therapist_token)

    response = client.post(
        f"/patients/{patient_id}/assistant",
        json={"question": "How do I use crutches?"},
        headers=_auth_headers(therapist_token),
    )

    assert response.status_code == 403


def test_ask_assistant_rejects_non_owning_patient() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, _ = _create_and_activate_patient(therapist_token)
    other_patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.post(
        f"/patients/{patient_id}/assistant",
        json={"question": "How do I use crutches?"},
        headers=_auth_headers(other_patient_token),
    )

    assert response.status_code == 403


def test_ask_assistant_rejects_unknown_patient() -> None:
    unknown_patient_id = uuid.uuid4()
    token = create_access_token(subject=str(unknown_patient_id), role="patient")

    response = client.post(
        f"/patients/{unknown_patient_id}/assistant",
        json={"question": "How do I use crutches?"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def _flag_a_question(therapist_token: str, patient_id: str, patient_token: str) -> str:
    response = client.post(
        f"/patients/{patient_id}/assistant",
        json={"question": "My incision is red and draining, is that normal?"},
        headers=_auth_headers(patient_token),
    )
    return response.json()["id"]


def test_list_flagged_questions_as_owning_therapist() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)
    interaction_id = _flag_a_question(therapist_token, patient_id, patient_token)

    response = client.get(
        f"/patients/{patient_id}/assistant/flagged-questions",
        headers=_auth_headers(therapist_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == interaction_id
    assert "incision" in body[0]["question"]


def test_list_flagged_questions_rejects_patient_role() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)

    response = client.get(
        f"/patients/{patient_id}/assistant/flagged-questions",
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 403


def test_list_flagged_questions_rejects_non_owning_therapist() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)
    _flag_a_question(therapist_token, patient_id, patient_token)

    other_therapist_token = _signup_and_login_therapist()
    response = client.get(
        f"/patients/{patient_id}/assistant/flagged-questions",
        headers=_auth_headers(other_therapist_token),
    )

    assert response.status_code == 404


def test_acknowledge_flagged_question_removes_it_from_the_list() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)
    interaction_id = _flag_a_question(therapist_token, patient_id, patient_token)

    ack_response = client.post(
        f"/patients/{patient_id}/assistant/flagged-questions/{interaction_id}/acknowledge",
        headers=_auth_headers(therapist_token),
    )
    assert ack_response.status_code == 200, ack_response.text
    assert ack_response.json()["id"] == interaction_id

    list_response = client.get(
        f"/patients/{patient_id}/assistant/flagged-questions",
        headers=_auth_headers(therapist_token),
    )
    assert list_response.json() == []


def test_acknowledge_flagged_question_rejects_double_acknowledge() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, patient_token = _create_and_activate_patient(therapist_token)
    interaction_id = _flag_a_question(therapist_token, patient_id, patient_token)

    client.post(
        f"/patients/{patient_id}/assistant/flagged-questions/{interaction_id}/acknowledge",
        headers=_auth_headers(therapist_token),
    )
    response = client.post(
        f"/patients/{patient_id}/assistant/flagged-questions/{interaction_id}/acknowledge",
        headers=_auth_headers(therapist_token),
    )

    assert response.status_code == 409


def test_acknowledge_flagged_question_rejects_unknown_interaction() -> None:
    therapist_token = _signup_and_login_therapist()
    patient_id, _patient_token = _create_and_activate_patient(therapist_token)

    response = client.post(
        f"/patients/{patient_id}/assistant/flagged-questions/{uuid.uuid4()}/acknowledge",
        headers=_auth_headers(therapist_token),
    )

    assert response.status_code == 404

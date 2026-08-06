import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.copilot import commands as copilot_commands
from app.core.config import settings
from app.core.llm_client import CopilotAnswer
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


def _create_patient(token: str) -> str:
    payload = {
        "name": "Pat Patient",
        "date_of_birth": "1990-01-01",
        "contact_email": f"patient-{uuid.uuid4()}@example.com",
        "surgery_date": (date.today() + timedelta(days=14)).isoformat(),
    }
    response = client.post("/patients", json=payload, headers=_auth_headers(token))
    return response.json()["id"]


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(copilot_commands, "embed_text", lambda text, **kw: list(FAKE_EMBEDDING))
    monkeypatch.setattr(
        copilot_commands,
        "answer_copilot_message",
        lambda **kwargs: CopilotAnswer(answer="Grounded answer."),
    )


def test_post_message_as_owning_therapist() -> None:
    token = _signup_and_login_therapist()
    patient_id = _create_patient(token)

    response = client.post(
        f"/patients/{patient_id}/copilot/messages",
        json={"content": "Any restrictions?"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["patient_id"] == patient_id
    assert body["role"] == "assistant"
    assert body["content"] == "Grounded answer."


def test_list_messages_returns_ordered_thread() -> None:
    token = _signup_and_login_therapist()
    patient_id = _create_patient(token)
    client.post(
        f"/patients/{patient_id}/copilot/messages",
        json={"content": "Any restrictions?"},
        headers=_auth_headers(token),
    )

    response = client.get(f"/patients/{patient_id}/copilot/messages", headers=_auth_headers(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [m["role"] for m in body] == ["therapist", "assistant"]
    assert body[0]["content"] == "Any restrictions?"


def test_post_message_rejects_non_owning_therapist() -> None:
    token_a = _signup_and_login_therapist()
    token_b = _signup_and_login_therapist()
    patient_id = _create_patient(token_a)

    response = client.post(
        f"/patients/{patient_id}/copilot/messages",
        json={"content": "Any restrictions?"},
        headers=_auth_headers(token_b),
    )

    assert response.status_code == 404


def test_post_message_rejects_patient_role() -> None:
    token = _signup_and_login_therapist()
    patient_id = _create_patient(token)
    patient_token = create_access_token(subject=str(uuid.uuid4()), role="patient")

    response = client.post(
        f"/patients/{patient_id}/copilot/messages",
        json={"content": "Any restrictions?"},
        headers=_auth_headers(patient_token),
    )

    assert response.status_code == 403

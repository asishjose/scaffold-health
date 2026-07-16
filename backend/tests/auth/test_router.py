import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def _unique_email() -> str:
    return f"therapist-{uuid.uuid4()}@example.com"


def _signup(email: str, password: str = "a-strong-password") -> dict:
    response = client.post(
        "/auth/signup",
        json={
            "name": "Dana Therapist",
            "email": email,
            "password": password,
            "registration_code": settings.clinic_registration_code,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_signup_creates_therapist() -> None:
    email = _unique_email()

    body = _signup(email)

    assert body["email"] == email
    assert "id" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_signup_rejects_bad_registration_code() -> None:
    response = client.post(
        "/auth/signup",
        json={
            "name": "Dana Therapist",
            "email": _unique_email(),
            "password": "a-strong-password",
            "registration_code": "WRONG-CODE",
        },
    )

    assert response.status_code == 403


def test_signup_rejects_duplicate_email() -> None:
    email = _unique_email()
    _signup(email)

    response = client.post(
        "/auth/signup",
        json={
            "name": "Someone Else",
            "email": email,
            "password": "another-password",
            "registration_code": settings.clinic_registration_code,
        },
    )

    assert response.status_code == 409


def test_login_issues_access_and_refresh_tokens() -> None:
    email = _unique_email()
    _signup(email, password="a-strong-password")

    response = client.post("/auth/login", json={"email": email, "password": "a-strong-password"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


def test_login_rejects_wrong_password() -> None:
    email = _unique_email()
    _signup(email, password="a-strong-password")

    response = client.post("/auth/login", json={"email": email, "password": "wrong-password"})

    assert response.status_code == 401


def test_login_rejects_unknown_email() -> None:
    response = client.post(
        "/auth/login", json={"email": _unique_email(), "password": "whatever-password"}
    )

    assert response.status_code == 401


def test_refresh_issues_new_access_token() -> None:
    email = _unique_email()
    _signup(email, password="a-strong-password")
    login_body = client.post(
        "/auth/login", json={"email": email, "password": "a-strong-password"}
    ).json()

    response = client.post("/auth/refresh", json={"refresh_token": login_body["refresh_token"]})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["access_token"] != login_body["access_token"]


def test_refresh_rejects_access_token() -> None:
    email = _unique_email()
    _signup(email, password="a-strong-password")
    login_body = client.post(
        "/auth/login", json={"email": email, "password": "a-strong-password"}
    ).json()

    response = client.post("/auth/refresh", json={"refresh_token": login_body["access_token"]})

    assert response.status_code == 401

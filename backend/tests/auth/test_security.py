import uuid

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import (
    CurrentUser,
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)


def test_hash_password_roundtrip() -> None:
    hashed = hash_password("correct-horse-battery-staple")

    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip() -> None:
    subject = str(uuid.uuid4())

    token = create_access_token(subject=subject, role="therapist")
    claims = decode_token(token, expected_type=TokenType.ACCESS)

    assert claims["sub"] == subject
    assert claims["role"] == "therapist"
    assert claims["type"] == "access"


def test_refresh_token_roundtrip() -> None:
    subject = str(uuid.uuid4())

    token = create_refresh_token(subject=subject, role="therapist")
    claims = decode_token(token, expected_type=TokenType.REFRESH)

    assert claims["sub"] == subject
    assert claims["type"] == "refresh"


def test_decode_token_rejects_wrong_type() -> None:
    access_token = create_access_token(subject=str(uuid.uuid4()), role="therapist")

    with pytest.raises(InvalidTokenError):
        decode_token(access_token, expected_type=TokenType.REFRESH)


def test_decode_token_rejects_bad_signature() -> None:
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "therapist", "type": "access"},
        "wrong-secret",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type=TokenType.ACCESS)


def test_decode_token_rejects_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    token = create_access_token(subject=str(uuid.uuid4()), role="therapist")

    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type=TokenType.ACCESS)


def test_get_current_user_accepts_valid_access_token() -> None:
    subject = uuid.uuid4()
    token = create_access_token(subject=str(subject), role="therapist")

    current_user = get_current_user(token=token)

    assert current_user == CurrentUser(id=subject, role="therapist")


def test_get_current_user_rejects_refresh_token() -> None:
    token = create_refresh_token(subject=str(uuid.uuid4()), role="therapist")

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=token)

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_garbage_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token="not-a-jwt")

    assert exc_info.value.status_code == 401

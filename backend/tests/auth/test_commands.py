import uuid

import pytest
from sqlalchemy.orm import Session

from app.auth import commands
from app.core.config import settings
from app.core.security import verify_password
from app.event_store.store import get_stream_events


def _unique_email() -> str:
    return f"therapist-{uuid.uuid4()}@example.com"


def test_register_therapist_appends_event_and_projects_read_model(db: Session) -> None:
    email = _unique_email()

    therapist = commands.register_therapist(
        db,
        name="Dana Therapist",
        email=email,
        password="a-strong-password",
        registration_code=settings.clinic_registration_code,
    )

    assert therapist.email == email
    assert verify_password("a-strong-password", therapist.password_hash)

    events = get_stream_events(db, stream_id=therapist.id)
    assert len(events) == 1
    assert events[0].event_type == "TherapistRegistered"
    assert events[0].payload["email"] == email
    assert events[0].payload["password_hash"] == therapist.password_hash


def test_register_therapist_normalizes_email(db: Session) -> None:
    raw_email = f"  Mixed.Case-{uuid.uuid4()}@Example.com  "

    therapist = commands.register_therapist(
        db,
        name="Dana Therapist",
        email=raw_email,
        password="a-strong-password",
        registration_code=settings.clinic_registration_code,
    )

    assert therapist.email == raw_email.strip().lower()


def test_register_therapist_rejects_invalid_registration_code(db: Session) -> None:
    with pytest.raises(commands.InvalidRegistrationCode):
        commands.register_therapist(
            db,
            name="Dana Therapist",
            email=_unique_email(),
            password="a-strong-password",
            registration_code="WRONG-CODE",
        )


def test_register_therapist_rejects_duplicate_email(db: Session) -> None:
    email = _unique_email()
    commands.register_therapist(
        db,
        name="Dana Therapist",
        email=email,
        password="a-strong-password",
        registration_code=settings.clinic_registration_code,
    )

    with pytest.raises(commands.EmailAlreadyRegistered):
        commands.register_therapist(
            db,
            name="Someone Else",
            email=email,
            password="another-password",
            registration_code=settings.clinic_registration_code,
        )

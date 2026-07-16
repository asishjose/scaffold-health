import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.core.config import settings
from app.core.security import verify_password
from app.event_store.store import get_stream_events
from app.patients import commands, service


def _make_therapist(db: Session) -> uuid.UUID:
    therapist = auth_commands.register_therapist(
        db,
        name="Dana Therapist",
        email=f"therapist-{uuid.uuid4()}@example.com",
        password="a-strong-password",
        registration_code=settings.clinic_registration_code,
    )
    return therapist.id


def _intake_kwargs(therapist_id: uuid.UUID) -> dict:
    return {
        "therapist_id": therapist_id,
        "name": "Pat Patient",
        "date_of_birth": date(1990, 1, 1),
        "contact_email": f"patient-{uuid.uuid4()}@example.com",
        "surgery_date": date.today() + timedelta(days=14),
    }


def test_create_patient_appends_event_and_projects_read_model(db: Session) -> None:
    therapist_id = _make_therapist(db)

    patient = commands.create_patient(db, **_intake_kwargs(therapist_id))

    assert patient.therapist_id == therapist_id
    assert patient.injury == "acl_reconstruction"
    assert patient.current_phase == "pre_op"
    assert patient.invite_accepted_at is None

    events = get_stream_events(db, stream_id=patient.id)
    assert len(events) == 1
    assert events[0].event_type == "PatientCreated"
    assert events[0].payload["therapist_id"] == str(therapist_id)


def test_create_patient_normalizes_contact_email(db: Session) -> None:
    therapist_id = _make_therapist(db)
    kwargs = _intake_kwargs(therapist_id)
    kwargs["contact_email"] = f"  Mixed.Case-{uuid.uuid4()}@Example.com  "

    patient = commands.create_patient(db, **kwargs)

    assert patient.contact_email == kwargs["contact_email"].strip().lower()


def test_create_patient_rejects_unknown_therapist(db: Session) -> None:
    with pytest.raises(commands.TherapistNotFound):
        commands.create_patient(db, **_intake_kwargs(uuid.uuid4()))


def test_activate_patient_account_success(db: Session) -> None:
    therapist_id = _make_therapist(db)
    patient = commands.create_patient(db, **_intake_kwargs(therapist_id))

    activated = commands.activate_patient_account(
        db, invite_token=patient.invite_token, password="patient-password"
    )

    assert activated.invite_accepted_at is not None
    assert verify_password("patient-password", activated.password_hash)

    events = get_stream_events(db, stream_id=patient.id)
    assert [e.event_type for e in events] == ["PatientCreated", "PatientAccountActivated"]


def test_activate_patient_account_rejects_unknown_token(db: Session) -> None:
    with pytest.raises(service.InviteNotFound):
        commands.activate_patient_account(db, invite_token="not-a-real-token", password="x" * 10)


def test_activate_patient_account_rejects_reused_token(db: Session) -> None:
    therapist_id = _make_therapist(db)
    patient = commands.create_patient(db, **_intake_kwargs(therapist_id))
    commands.activate_patient_account(
        db, invite_token=patient.invite_token, password="patient-password"
    )

    with pytest.raises(service.InviteAlreadyUsed):
        commands.activate_patient_account(
            db, invite_token=patient.invite_token, password="another-password"
        )


def test_activate_patient_account_rejects_expired_token(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "invite_token_expire_hours", -1)
    therapist_id = _make_therapist(db)
    patient = commands.create_patient(db, **_intake_kwargs(therapist_id))

    with pytest.raises(service.InviteExpired):
        commands.activate_patient_account(
            db, invite_token=patient.invite_token, password="patient-password"
        )

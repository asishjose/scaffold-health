import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.checkins import commands
from app.core.config import settings
from app.event_store.store import get_stream_events
from app.patients import commands as patient_commands
from app.query_api.therapist import list_checkins


def _make_patient(db: Session) -> tuple[uuid.UUID, uuid.UUID]:
    therapist = auth_commands.register_therapist(
        db,
        name="Dana Therapist",
        email=f"therapist-{uuid.uuid4()}@example.com",
        password="a-strong-password",
        registration_code=settings.clinic_registration_code,
    )
    patient = patient_commands.create_patient(
        db,
        therapist_id=therapist.id,
        name="Pat Patient",
        date_of_birth=date(1990, 1, 1),
        contact_email=f"patient-{uuid.uuid4()}@example.com",
        surgery_date=date.today() + timedelta(days=14),
    )
    return therapist.id, patient.id


def test_submit_checkin_appends_event_and_projects_read_model(db: Session) -> None:
    _, patient_id = _make_patient(db)

    checkin = commands.submit_checkin(
        db, patient_id=patient_id, pain_level=4, note="feeling stiff"
    )

    assert checkin.patient_id == patient_id
    assert checkin.pain_level == 4
    assert checkin.note == "feeling stiff"

    events = get_stream_events(db, stream_id=checkin.id)
    assert len(events) == 1
    assert events[0].event_type == "CheckInSubmitted"


def test_submit_checkin_allows_no_note(db: Session) -> None:
    _, patient_id = _make_patient(db)

    checkin = commands.submit_checkin(db, patient_id=patient_id, pain_level=0, note=None)

    assert checkin.note is None


def test_submit_checkin_accumulates_multiple_entries(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)

    commands.submit_checkin(db, patient_id=patient_id, pain_level=5, note="day 1")
    commands.submit_checkin(db, patient_id=patient_id, pain_level=3, note="day 2")

    checkins = list_checkins(db, therapist_id=therapist_id, patient_id=patient_id)
    assert [c.pain_level for c in checkins] == [5, 3]


def test_submit_checkin_rejects_unknown_patient(db: Session) -> None:
    with pytest.raises(commands.PatientNotFound):
        commands.submit_checkin(db, patient_id=uuid.uuid4(), pain_level=5, note=None)

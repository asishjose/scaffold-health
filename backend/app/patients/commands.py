import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Therapist
from app.core.config import settings
from app.core.security import hash_password
from app.event_store.store import append_event
from app.patients import projector, service
from app.patients.events import (
    INITIAL_PHASE,
    INJURY_ACL_RECONSTRUCTION,
    PATIENT_ACCOUNT_ACTIVATED,
    PATIENT_CREATED,
    PATIENT_PHASE_ADVANCED,
    PHASE_SEQUENCE,
    STREAM_TYPE_PATIENT,
)
from app.patients.models import Patient
from app.timeline import projector as timeline_projector


class TherapistNotFound(Exception):
    pass


class PatientNotFound(Exception):
    pass


class InvalidPhaseTransition(Exception):
    pass


def create_patient(
    db: Session,
    *,
    therapist_id: uuid.UUID,
    name: str,
    date_of_birth: date,
    contact_email: str,
    surgery_date: date,
) -> Patient:
    if db.get(Therapist, therapist_id) is None:
        raise TherapistNotFound()

    invite_token = secrets.token_urlsafe(32)
    invite_expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.invite_token_expire_hours
    )

    event = append_event(
        db,
        stream_id=uuid.uuid4(),
        stream_type=STREAM_TYPE_PATIENT,
        event_type=PATIENT_CREATED,
        payload={
            "therapist_id": str(therapist_id),
            "name": name,
            "date_of_birth": date_of_birth.isoformat(),
            "contact_email": contact_email.strip().lower(),
            "injury": INJURY_ACL_RECONSTRUCTION,
            "surgery_date": surgery_date.isoformat(),
            "current_phase": INITIAL_PHASE,
            "invite_token": invite_token,
            "invite_expires_at": invite_expires_at.isoformat(),
        },
        actor_id=therapist_id,
        actor_role="therapist",
    )
    patient = projector.apply(db, event)
    db.commit()

    return patient


def activate_patient_account(db: Session, *, invite_token: str, password: str) -> Patient:
    patient = service.get_patient_by_invite_token(db, invite_token=invite_token)

    event = append_event(
        db,
        stream_id=patient.id,
        stream_type=STREAM_TYPE_PATIENT,
        event_type=PATIENT_ACCOUNT_ACTIVATED,
        payload={"password_hash": hash_password(password)},
        actor_id=patient.id,
        actor_role="patient",
    )
    patient = projector.apply(db, event)
    db.commit()

    return patient


def advance_phase(
    db: Session,
    *,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    target_phase: str,
    note: str | None,
) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.therapist_id == therapist_id)
    ).scalar_one_or_none()
    if patient is None:
        raise PatientNotFound()

    try:
        current_index = PHASE_SEQUENCE.index(patient.current_phase)
    except ValueError:
        raise InvalidPhaseTransition() from None

    if current_index + 1 >= len(PHASE_SEQUENCE):
        raise InvalidPhaseTransition()

    next_phase = PHASE_SEQUENCE[current_index + 1]
    if target_phase != next_phase:
        raise InvalidPhaseTransition()

    event = append_event(
        db,
        stream_id=patient.id,
        stream_type=STREAM_TYPE_PATIENT,
        event_type=PATIENT_PHASE_ADVANCED,
        payload={"from_phase": patient.current_phase, "to_phase": next_phase, "note": note},
        actor_id=therapist_id,
        actor_role="therapist",
    )
    patient = projector.apply(db, event)
    timeline_projector.apply(db, event)
    db.commit()

    return patient

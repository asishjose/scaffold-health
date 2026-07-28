import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.event_store.models import Event
from app.patients.events import (
    PATIENT_ACCOUNT_ACTIVATED,
    PATIENT_CREATED,
    PATIENT_PHASE_ADVANCED,
)
from app.patients.models import Patient


def apply(db: Session, event: Event) -> Patient | None:
    """Applies one event to the patients read model. Called synchronously
    right after the causing event is appended, and (eventually) by full
    replay.
    """
    if event.event_type == PATIENT_CREATED:
        return _apply_patient_created(db, event)
    if event.event_type == PATIENT_ACCOUNT_ACTIVATED:
        return _apply_patient_account_activated(db, event)
    if event.event_type == PATIENT_PHASE_ADVANCED:
        return _apply_patient_phase_advanced(db, event)
    return None


def _apply_patient_created(db: Session, event: Event) -> Patient:
    payload = event.payload
    patient = Patient(
        id=event.stream_id,
        therapist_id=uuid.UUID(payload["therapist_id"]),
        name=payload["name"],
        date_of_birth=datetime.fromisoformat(payload["date_of_birth"]).date(),
        contact_email=payload["contact_email"],
        injury=payload["injury"],
        surgery_date=datetime.fromisoformat(payload["surgery_date"]).date(),
        current_phase=payload["current_phase"],
        invite_token=payload["invite_token"],
        invite_expires_at=datetime.fromisoformat(payload["invite_expires_at"]),
    )
    db.add(patient)
    db.flush()
    return patient


def _apply_patient_account_activated(db: Session, event: Event) -> Patient:
    patient = db.get(Patient, event.stream_id)
    patient.password_hash = event.payload["password_hash"]
    patient.invite_accepted_at = event.created_at
    db.flush()
    return patient


def _apply_patient_phase_advanced(db: Session, event: Event) -> Patient:
    patient = db.get(Patient, event.stream_id)
    patient.current_phase = event.payload["to_phase"]
    db.flush()
    return patient

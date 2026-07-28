import uuid

from sqlalchemy.orm import Session

from app.checkins import projector
from app.checkins.events import CHECKIN_SUBMITTED, STREAM_TYPE_CHECKIN
from app.checkins.models import CheckIn
from app.event_store.store import append_event
from app.patients.models import Patient


class PatientNotFound(Exception):
    pass


def submit_checkin(
    db: Session, *, patient_id: uuid.UUID, pain_level: int, note: str | None
) -> CheckIn:
    if db.get(Patient, patient_id) is None:
        raise PatientNotFound()

    event = append_event(
        db,
        stream_id=uuid.uuid4(),
        stream_type=STREAM_TYPE_CHECKIN,
        event_type=CHECKIN_SUBMITTED,
        payload={"patient_id": str(patient_id), "pain_level": pain_level, "note": note},
        actor_id=patient_id,
        actor_role="patient",
    )
    checkin = projector.apply(db, event)
    db.commit()

    return checkin

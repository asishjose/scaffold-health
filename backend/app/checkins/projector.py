import uuid

from sqlalchemy.orm import Session

from app.checkins.events import CHECKIN_SUBMITTED
from app.checkins.models import CheckIn
from app.event_store.models import Event


def apply(db: Session, event: Event) -> CheckIn | None:
    """Applies one event to the checkins read model. Called synchronously
    right after the causing event is appended, and (eventually) by full
    replay.
    """
    if event.event_type == CHECKIN_SUBMITTED:
        return _apply_checkin_submitted(db, event)
    return None


def _apply_checkin_submitted(db: Session, event: Event) -> CheckIn:
    payload = event.payload
    checkin = CheckIn(
        id=event.stream_id,
        patient_id=uuid.UUID(payload["patient_id"]),
        pain_level=payload["pain_level"],
        note=payload.get("note"),
        submitted_at=event.created_at,
    )
    db.add(checkin)
    db.flush()
    return checkin

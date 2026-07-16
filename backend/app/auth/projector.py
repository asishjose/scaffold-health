from sqlalchemy.orm import Session

from app.auth.events import THERAPIST_REGISTERED
from app.auth.models import Therapist
from app.event_store.models import Event


def apply(db: Session, event: Event) -> Therapist | None:
    """Applies one event to the auth read models. Called synchronously right
    after the causing event is appended, and (eventually) by full replay.
    """
    if event.event_type == THERAPIST_REGISTERED:
        return _apply_therapist_registered(db, event)
    return None


def _apply_therapist_registered(db: Session, event: Event) -> Therapist:
    therapist = Therapist(
        id=event.stream_id,
        name=event.payload["name"],
        email=event.payload["email"],
        password_hash=event.payload["password_hash"],
    )
    db.add(therapist)
    db.flush()
    return therapist

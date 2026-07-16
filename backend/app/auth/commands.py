import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import projector
from app.auth.events import STREAM_TYPE_THERAPIST, THERAPIST_REGISTERED
from app.auth.models import Therapist
from app.core.config import settings
from app.core.security import hash_password
from app.event_store.store import append_event


class InvalidRegistrationCode(Exception):
    pass


class EmailAlreadyRegistered(Exception):
    pass


def register_therapist(
    db: Session, *, name: str, email: str, password: str, registration_code: str
) -> Therapist:
    if registration_code != settings.clinic_registration_code:
        raise InvalidRegistrationCode()

    normalized_email = email.strip().lower()
    existing = db.execute(
        select(Therapist).where(Therapist.email == normalized_email)
    ).scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyRegistered()

    event = append_event(
        db,
        stream_id=uuid.uuid4(),
        stream_type=STREAM_TYPE_THERAPIST,
        event_type=THERAPIST_REGISTERED,
        payload={
            "name": name,
            "email": normalized_email,
            "password_hash": hash_password(password),
        },
    )
    therapist = projector.apply(db, event)
    db.commit()

    return therapist

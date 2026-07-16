from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.patients.models import Patient


class InviteNotFound(Exception):
    pass


class InviteExpired(Exception):
    pass


class InviteAlreadyUsed(Exception):
    pass


def get_patient_by_invite_token(db: Session, *, invite_token: str) -> Patient:
    """Looks up a patient by invite token and validates the invite is still
    usable. Shared by the invite-preview and invite-acceptance flows so both
    apply the same expiry/reuse rules.
    """
    patient = db.execute(
        select(Patient).where(Patient.invite_token == invite_token)
    ).scalar_one_or_none()
    if patient is None:
        raise InviteNotFound()

    if patient.invite_accepted_at is not None:
        raise InviteAlreadyUsed()

    if datetime.now(timezone.utc) > patient.invite_expires_at:
        raise InviteExpired()

    return patient


def authenticate_patient(db: Session, *, email: str, password: str) -> Patient | None:
    patient = db.execute(
        select(Patient).where(Patient.contact_email == email.strip().lower())
    ).scalar_one_or_none()
    if patient is None or patient.password_hash is None:
        return None
    if not verify_password(password, patient.password_hash):
        return None
    return patient

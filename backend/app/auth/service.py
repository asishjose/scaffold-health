from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Therapist
from app.core.security import verify_password


def authenticate_therapist(db: Session, *, email: str, password: str) -> Therapist | None:
    therapist = db.execute(
        select(Therapist).where(Therapist.email == email.strip().lower())
    ).scalar_one_or_none()
    if therapist is None or not verify_password(password, therapist.password_hash):
        return None
    return therapist

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.patients.models import Patient


def get_own_patient(db: Session, *, patient_id: uuid.UUID) -> Patient | None:
    return db.execute(select(Patient).where(Patient.id == patient_id)).scalar_one_or_none()

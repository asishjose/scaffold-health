import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checkins.models import CheckIn
from app.patients.models import Patient


def get_own_patient(db: Session, *, patient_id: uuid.UUID) -> Patient | None:
    return db.execute(select(Patient).where(Patient.id == patient_id)).scalar_one_or_none()


def list_own_checkins(db: Session, *, patient_id: uuid.UUID) -> list[CheckIn]:
    return list(
        db.execute(
            select(CheckIn)
            .where(CheckIn.patient_id == patient_id)
            .order_by(CheckIn.submitted_at)
        ).scalars()
    )

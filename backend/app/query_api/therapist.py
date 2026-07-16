import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.patients.models import Patient


def list_caseload(db: Session, *, therapist_id: uuid.UUID) -> list[Patient]:
    return list(
        db.execute(
            select(Patient)
            .where(Patient.therapist_id == therapist_id)
            .order_by(Patient.created_at)
        ).scalars()
    )


def get_patient_detail(db: Session, *, therapist_id: uuid.UUID, patient_id: uuid.UUID) -> Patient | None:
    return db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.therapist_id == therapist_id)
    ).scalar_one_or_none()

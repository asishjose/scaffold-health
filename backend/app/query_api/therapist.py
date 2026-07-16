import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checkins.models import CheckIn
from app.documents.models import Document
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


def list_documents(
    db: Session, *, therapist_id: uuid.UUID, patient_id: uuid.UUID
) -> list[Document]:
    return list(
        db.execute(
            select(Document)
            .where(Document.patient_id == patient_id, Document.therapist_id == therapist_id)
            .order_by(Document.created_at)
        ).scalars()
    )


def list_checkins(db: Session, *, therapist_id: uuid.UUID, patient_id: uuid.UUID) -> list[CheckIn]:
    return list(
        db.execute(
            select(CheckIn)
            .join(Patient, Patient.id == CheckIn.patient_id)
            .where(CheckIn.patient_id == patient_id, Patient.therapist_id == therapist_id)
            .order_by(CheckIn.submitted_at)
        ).scalars()
    )

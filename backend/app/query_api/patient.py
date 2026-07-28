import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checkins.models import CheckIn
from app.patients.models import Patient
from app.rag.events import SCOPE_PATIENT_EDUCATION
from app.rag.models import RagChunk
from app.timeline.models import TimelineEntry

DEFAULT_RETRIEVAL_LIMIT = 8


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


def list_own_timeline_entries(db: Session, *, patient_id: uuid.UUID) -> list[TimelineEntry]:
    return list(
        db.execute(
            select(TimelineEntry)
            .where(TimelineEntry.patient_id == patient_id)
            .order_by(TimelineEntry.occurred_at)
        ).scalars()
    )


def retrieve_patient_education_chunks(
    db: Session, *, query_embedding: list[float], limit: int = DEFAULT_RETRIEVAL_LIMIT
) -> list[RagChunk]:
    """Nearest-neighbor retrieval over the shared patient-education corpus
    (Patient Assistant-only, PRD §6.4).
    """
    return list(
        db.execute(
            select(RagChunk)
            .where(RagChunk.scope == SCOPE_PATIENT_EDUCATION)
            .order_by(RagChunk.embedding.cosine_distance(query_embedding))
            .limit(limit)
        ).scalars()
    )

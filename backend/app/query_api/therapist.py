import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.checkins.models import CheckIn
from app.documents.models import Document
from app.patients.events import PHASE_SEQUENCE
from app.patients.models import Patient
from app.profile import derived
from app.profile.models import ProfileField
from app.rag.events import SCOPE_CLINICAL_GUIDELINES, SCOPE_PATIENT_NOTES
from app.rag.models import RagChunk

DISCHARGED_PHASE = PHASE_SEQUENCE[-1]
DEFAULT_RETRIEVAL_LIMIT = 8


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


def list_profile_fields(
    db: Session, *, therapist_id: uuid.UUID, patient_id: uuid.UUID
) -> list[ProfileField]:
    return list(
        db.execute(
            select(ProfileField)
            .where(
                ProfileField.patient_id == patient_id, ProfileField.therapist_id == therapist_id
            )
            .order_by(ProfileField.extracted_at)
        ).scalars()
    )


def current_field_values(profile_fields: list[ProfileField], field_name: str) -> list[str]:
    """Non-superseded values for one field, in extraction order — the
    accumulated set for an overwrite/append-only field right now.
    """
    return [f.value for f in profile_fields if f.field_name == field_name and f.superseded_at is None]


def retrieve_patient_notes_chunks(
    db: Session,
    *,
    therapist_id: uuid.UUID,
    patient_id: uuid.UUID,
    query_embedding: list[float],
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> list[RagChunk]:
    """Nearest-neighbor retrieval over one patient's document/note residual
    text, hard-scoped by both patient_id and therapist_id in the query
    itself (PRD §10) — never post-filtered.
    """
    return list(
        db.execute(
            select(RagChunk)
            .where(
                RagChunk.scope == SCOPE_PATIENT_NOTES,
                RagChunk.patient_id == patient_id,
                RagChunk.therapist_id == therapist_id,
            )
            .order_by(RagChunk.embedding.cosine_distance(query_embedding))
            .limit(limit)
        ).scalars()
    )


def retrieve_clinical_guideline_chunks(
    db: Session, *, query_embedding: list[float], limit: int = DEFAULT_RETRIEVAL_LIMIT
) -> list[RagChunk]:
    """Nearest-neighbor retrieval over the shared clinical-guideline corpus
    (Copilot-only, PRD §6.4).
    """
    return list(
        db.execute(
            select(RagChunk)
            .where(RagChunk.scope == SCOPE_CLINICAL_GUIDELINES)
            .order_by(RagChunk.embedding.cosine_distance(query_embedding))
            .limit(limit)
        ).scalars()
    )


def list_needs_review_reasons(
    db: Session, *, therapist_id: uuid.UUID, patients: list[Patient]
) -> dict[uuid.UUID, list[str]]:
    """Typed needs_review reasons for every patient in `patients`, computed
    with three aggregate queries total rather than one round-trip per
    patient.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=derived.ADHERENCE_WINDOW_DAYS)

    contradiction_patient_ids = set(
        db.execute(
            select(ProfileField.patient_id)
            .where(ProfileField.therapist_id == therapist_id, ProfileField.is_contradiction.is_(True))
            .distinct()
        ).scalars()
    )

    recent_checkin_counts = dict(
        db.execute(
            select(CheckIn.patient_id, func.count(CheckIn.id))
            .join(Patient, Patient.id == CheckIn.patient_id)
            .where(Patient.therapist_id == therapist_id, CheckIn.submitted_at >= window_start)
            .group_by(CheckIn.patient_id)
        ).all()
    )

    return {
        patient.id: derived.compute_needs_review_reasons(
            has_contradiction=patient.id in contradiction_patient_ids,
            invite_accepted_at=patient.invite_accepted_at,
            is_discharged=patient.current_phase == DISCHARGED_PHASE,
            recent_checkin_count=recent_checkin_counts.get(patient.id, 0),
            now=now,
        )
        for patient in patients
    }

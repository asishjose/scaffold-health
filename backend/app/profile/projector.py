import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.event_store.models import Event
from app.profile.events import CONTRADICTION_ACKNOWLEDGED, PROFILE_FIELDS_MERGED, STRATEGY_OVERWRITE
from app.profile.models import ProfileField


def apply(db: Session, event: Event) -> list[ProfileField]:
    """Applies one event to the profile_fields read model. Called
    synchronously right after the causing event is appended, and
    (eventually) by full replay. Unlike other projectors this returns a
    list — one ProfileFieldsMerged event can carry a batch of facts for the
    same field, each projected into its own row for per-fact provenance.
    """
    if event.event_type == PROFILE_FIELDS_MERGED:
        return _apply_profile_fields_merged(db, event)
    if event.event_type == CONTRADICTION_ACKNOWLEDGED:
        return _apply_contradiction_acknowledged(db, event)
    return []


def _apply_profile_fields_merged(db: Session, event: Event) -> list[ProfileField]:
    payload = event.payload
    field_name = payload["field_name"]
    strategy = payload["merge_strategy"]

    if strategy == STRATEGY_OVERWRITE:
        db.execute(
            update(ProfileField)
            .where(
                ProfileField.patient_id == event.stream_id,
                ProfileField.field_name == field_name,
                ProfileField.superseded_at.is_(None),
            )
            .values(superseded_at=event.created_at)
        )

    source_document_id = payload.get("source_document_id")
    extracted_at = datetime.fromisoformat(payload["extracted_at"])

    rows = []
    for fact in payload["facts"]:
        row = ProfileField(
            id=uuid.uuid4(),
            patient_id=event.stream_id,
            therapist_id=uuid.UUID(payload["therapist_id"]),
            field_name=field_name,
            value=fact["value"],
            confidence=fact.get("confidence"),
            source_quote=fact.get("source_quote"),
            source_document_id=uuid.UUID(source_document_id) if source_document_id else None,
            source_event_id=event.id,
            extractor_version=payload["extractor_version"],
            extracted_at=extracted_at,
            is_contradiction=fact.get("is_contradiction", False),
        )
        db.add(row)
        rows.append(row)

    db.flush()
    return rows


def _apply_contradiction_acknowledged(db: Session, event: Event) -> list[ProfileField]:
    field = db.get(ProfileField, uuid.UUID(event.payload["profile_field_id"]))
    field.acknowledged_at = event.created_at
    db.flush()
    return [field]

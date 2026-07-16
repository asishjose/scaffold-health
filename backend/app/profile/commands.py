from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.llm_client import ExtractedFact
from app.documents.models import Document
from app.event_store.store import append_event
from app.patients.models import Patient
from app.profile import projector
from app.profile.events import (
    EXTRACTABLE_FIELDS,
    FIELD_MERGE_STRATEGIES,
    PROFILE_FIELDS_MERGED,
    STREAM_TYPE_PROFILE,
    STRATEGY_APPEND_ONLY,
    STRATEGY_IMMUTABLE_ONCE_SET,
)
from app.profile.models import ProfileField

EXTRACTOR_VERSION = "gemini-fact-extraction-v1"


def merge_extracted_facts(
    db: Session,
    *,
    patient: Patient,
    document: Document,
    facts: list[ExtractedFact],
    extracted_at: datetime,
) -> list[ProfileField]:
    """Deterministic merge routing (PRD §9: "the LLM never decides how a
    conflict is resolved or which merge strategy applies — that mapping is
    fixed Python logic keyed by field name"). Groups candidate facts by
    field and writes one ProfileFieldsMerged event per field, so an
    overwrite-strategy field's whole batch from this document replaces the
    prior set atomically rather than one fact superseding the last.
    """
    by_field: dict[str, list[ExtractedFact]] = defaultdict(list)
    for fact in facts:
        if fact.field_name in EXTRACTABLE_FIELDS:
            by_field[fact.field_name].append(fact)

    written: list[ProfileField] = []
    for field_name, field_facts in by_field.items():
        strategy = FIELD_MERGE_STRATEGIES[field_name]

        if strategy == STRATEGY_APPEND_ONLY:
            field_facts = _dedupe_against_existing(
                db, patient_id=patient.id, field_name=field_name, facts=field_facts
            )

        if not field_facts:
            continue

        event = append_event(
            db,
            stream_id=patient.id,
            stream_type=STREAM_TYPE_PROFILE,
            event_type=PROFILE_FIELDS_MERGED,
            payload={
                "field_name": field_name,
                "merge_strategy": strategy,
                "therapist_id": str(patient.therapist_id),
                "source_document_id": str(document.id),
                "extractor_version": EXTRACTOR_VERSION,
                "extracted_at": extracted_at.isoformat(),
                "facts": [
                    _fact_payload(strategy, patient, field_name, fact) for fact in field_facts
                ],
            },
        )
        written.extend(projector.apply(db, event))

    db.commit()
    return written


def _fact_payload(strategy: str, patient: Patient, field_name: str, fact: ExtractedFact) -> dict:
    is_contradiction = (
        _conflicts_with_baseline(patient, field_name, fact.value)
        if strategy == STRATEGY_IMMUTABLE_ONCE_SET
        else False
    )
    return {
        "value": fact.value,
        "confidence": fact.confidence,
        "source_quote": fact.source_quote,
        "is_contradiction": is_contradiction,
    }


# Injury is fixed to ACL reconstruction for the whole MVP (see
# app.patients.events.INJURY_ACL_RECONSTRUCTION) but is stored as a slug
# ("acl_reconstruction") while extraction returns free text ("right knee
# ACL reconstruction", "anterior cruciate ligament rupture", ...). Comparing
# by exact string would flag a contradiction on almost every real document
# purely from wording — so injury is treated as consistent whenever the
# extracted text plausibly describes the same ACL diagnosis.
_ACL_KEYWORDS = ("acl", "anterior cruciate ligament")


def _conflicts_with_baseline(patient: Patient, field_name: str, value: str) -> bool:
    """injury/surgery_date are set once at intake and never overwritten by
    extraction (PRD §6.3: immutable-once-set). A conflicting extracted value
    is never silently applied — it's recorded with is_contradiction=True so
    the therapist sees it and decides.
    """
    if field_name == "injury":
        lowered = value.strip().lower()
        return not any(keyword in lowered for keyword in _ACL_KEYWORDS)
    if field_name == "surgery_date":
        try:
            extracted_date = date.fromisoformat(value.strip())
        except ValueError:
            return False
        return extracted_date != patient.surgery_date
    return False


def _dedupe_against_existing(
    db: Session, *, patient_id, field_name: str, facts: list[ExtractedFact]
) -> list[ExtractedFact]:
    """Append-only fields (milestones) accumulate forever; skip facts that
    already exist verbatim so re-processing similar documents doesn't spam
    the timeline with duplicates.
    """
    existing = {
        value.strip().lower()
        for value in db.execute(
            select(ProfileField.value).where(
                ProfileField.patient_id == patient_id, ProfileField.field_name == field_name
            )
        ).scalars()
    }
    deduped = []
    seen: set[str] = set()
    for fact in facts:
        key = fact.value.strip().lower()
        if key in existing or key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped

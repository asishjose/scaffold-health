from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

import uuid

from app.core.llm_client import ExtractedFact
from app.documents.models import Document
from app.event_store.store import append_event
from app.patients.models import Patient
from app.profile import projector
from app.profile.events import (
    EXTRACTABLE_FIELDS,
    FIELD_MERGE_STRATEGIES,
    PENDING_STATUS_APPROVED,
    PENDING_STATUS_PENDING,
    PENDING_STATUS_REJECTED,
    PROFILE_FIELDS_MERGED,
    STREAM_TYPE_PROFILE,
    STRATEGY_APPEND_ONLY,
    STRATEGY_IMMUTABLE_ONCE_SET,
    STRATEGY_OVERWRITE,
)
from app.profile.models import PendingProfileFact, ProfileField
from app.timeline import projector as timeline_projector

EXTRACTOR_VERSION = "gemini-fact-extraction-v1"

# Facts below this confidence are held for therapist review instead of
# auto-merging — a plain module constant so it's easy to tune later (same
# convention as MEANINGFUL_PAIN_SHIFT/LOW_ADHERENCE_CHECKIN_THRESHOLD in
# profile/derived.py).
LOW_CONFIDENCE_THRESHOLD = 0.7


class PendingFactNotFound(Exception):
    pass


class PendingFactAlreadyResolved(Exception):
    pass


@dataclass
class MergeResult:
    merged: list[ProfileField]
    staged: list[PendingProfileFact]


def merge_extracted_facts(
    db: Session,
    *,
    patient: Patient,
    document: Document,
    facts: list[ExtractedFact],
    extracted_at: datetime,
) -> MergeResult:
    """Deterministic merge routing (PRD §9: "the LLM never decides how a
    conflict is resolved or which merge strategy applies — that mapping is
    fixed Python logic keyed by field name"). Facts that contradict the
    immutable baseline or fall below LOW_CONFIDENCE_THRESHOLD are held as
    PendingProfileFact rows instead of merging — nothing unverified reaches
    the Knowledge Profile (and therefore Copilot/Prep Briefs) until a
    therapist explicitly approves it.

    OVERWRITE-strategy fields (active_restrictions/active_concerns) stage
    their whole per-document batch together whenever any member is
    low-confidence, since an OVERWRITE merge event atomically replaces
    every currently-active value for that field — auto-merging only the
    confident subset would silently drop context the therapist hasn't
    reviewed yet. Non-OVERWRITE fields stage per fact.
    """
    by_field: dict[str, list[ExtractedFact]] = defaultdict(list)
    for fact in facts:
        if fact.field_name in EXTRACTABLE_FIELDS:
            by_field[fact.field_name].append(fact)

    merged: list[ProfileField] = []
    staged: list[PendingProfileFact] = []

    for field_name, field_facts in by_field.items():
        strategy = FIELD_MERGE_STRATEGIES[field_name]

        if strategy == STRATEGY_OVERWRITE:
            if any(fact.confidence < LOW_CONFIDENCE_THRESHOLD for fact in field_facts):
                for fact in field_facts:
                    staged.append(
                        _stage_fact(
                            db,
                            patient=patient,
                            document=document,
                            field_name=field_name,
                            fact=fact,
                            extracted_at=extracted_at,
                            is_contradiction=False,
                            is_low_confidence=fact.confidence < LOW_CONFIDENCE_THRESHOLD,
                        )
                    )
                continue
            merged.extend(
                _merge_field_facts(
                    db,
                    patient=patient,
                    document=document,
                    field_name=field_name,
                    facts=field_facts,
                    extracted_at=extracted_at,
                )
            )
            continue

        auto_facts = []
        for fact in field_facts:
            is_contradiction = (
                _conflicts_with_baseline(patient, field_name, fact.value)
                if strategy == STRATEGY_IMMUTABLE_ONCE_SET
                else False
            )
            is_low_confidence = fact.confidence < LOW_CONFIDENCE_THRESHOLD
            if is_contradiction or is_low_confidence:
                staged.append(
                    _stage_fact(
                        db,
                        patient=patient,
                        document=document,
                        field_name=field_name,
                        fact=fact,
                        extracted_at=extracted_at,
                        is_contradiction=is_contradiction,
                        is_low_confidence=is_low_confidence,
                    )
                )
            else:
                auto_facts.append(fact)

        merged.extend(
            _merge_field_facts(
                db,
                patient=patient,
                document=document,
                field_name=field_name,
                facts=auto_facts,
                extracted_at=extracted_at,
            )
        )

    db.commit()
    return MergeResult(merged=merged, staged=staged)


def _merge_field_facts(
    db: Session,
    *,
    patient: Patient,
    document: Document,
    field_name: str,
    facts: list[ExtractedFact],
    extracted_at: datetime,
) -> list[ProfileField]:
    """Writes one ProfileFieldsMerged event for `facts` (all for the same
    field) and applies it. Shared by the auto-merge path above and every
    approval path below, so merge-strategy routing and event-payload
    construction exist in exactly one place.
    """
    strategy = FIELD_MERGE_STRATEGIES[field_name]

    if strategy == STRATEGY_APPEND_ONLY:
        facts = _dedupe_against_existing(
            db, patient_id=patient.id, field_name=field_name, facts=facts
        )

    if not facts:
        return []

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
            "facts": [_fact_payload(strategy, patient, field_name, fact) for fact in facts],
        },
    )
    rows = projector.apply(db, event)
    timeline_projector.apply(db, event)
    return rows


def _fact_payload(strategy: str, patient: Patient, field_name: str, fact: ExtractedFact) -> dict:
    is_contradiction = (
        _conflicts_with_baseline(patient, field_name, fact.value)
        if strategy == STRATEGY_IMMUTABLE_ONCE_SET else False
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
    is never silently applied — it's held as a PendingProfileFact so the
    therapist sees it and decides.
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


def _stage_fact(
    db: Session,
    *,
    patient: Patient,
    document: Document,
    field_name: str,
    fact: ExtractedFact,
    extracted_at: datetime,
    is_contradiction: bool,
    is_low_confidence: bool,
) -> PendingProfileFact:
    row = PendingProfileFact(
        id=uuid.uuid4(),
        patient_id=patient.id,
        therapist_id=patient.therapist_id,
        source_document_id=document.id,
        field_name=field_name,
        value=fact.value,
        confidence=fact.confidence,
        source_quote=fact.source_quote,
        is_contradiction=is_contradiction,
        is_low_confidence=is_low_confidence,
        extractor_version=EXTRACTOR_VERSION,
        extracted_at=extracted_at,
        status=PENDING_STATUS_PENDING,
    )
    db.add(row)
    db.flush()
    return row


def _get_owned_pending_fact(
    db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID, fact_id: uuid.UUID
) -> PendingProfileFact:
    fact = db.execute(
        select(PendingProfileFact).where(
            PendingProfileFact.id == fact_id,
            PendingProfileFact.patient_id == patient_id,
            PendingProfileFact.therapist_id == therapist_id,
        )
    ).scalar_one_or_none()
    if fact is None:
        raise PendingFactNotFound()
    return fact


def approve_pending_fact(
    db: Session,
    *,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    fact_id: uuid.UUID,
    edited_value: str | None = None,
) -> PendingProfileFact:
    """Approves a staged fact, routing it through the same _merge_field_facts
    path used for auto-merged facts. Approving with an edited value that
    still conflicts with baseline is allowed, not blocked — clicking
    Approve *is* the explicit human override this feature exists to
    require.

    For OVERWRITE-strategy fields, the whole per-document batch a
    low-confidence fact belongs to was staged together (see
    merge_extracted_facts), so approving one row here only records the
    decision — the actual merge event fires once every row in that batch
    has been resolved (see _maybe_finalize_overwrite_batch), preserving the
    OVERWRITE atomic-replace guarantee.
    """
    fact = _get_owned_pending_fact(
        db, patient_id=patient_id, therapist_id=therapist_id, fact_id=fact_id
    )
    if fact.status != PENDING_STATUS_PENDING:
        raise PendingFactAlreadyResolved()

    final_value = edited_value.strip() if edited_value and edited_value.strip() else fact.value
    fact.status = PENDING_STATUS_APPROVED
    fact.resolved_at = datetime.now(timezone.utc)
    fact.resolved_by_id = therapist_id
    fact.resolved_value = final_value

    strategy = FIELD_MERGE_STRATEGIES[fact.field_name]
    if strategy == STRATEGY_OVERWRITE:
        _maybe_finalize_overwrite_batch(db, fact)
    else:
        patient = db.get(Patient, patient_id)
        document = db.get(Document, fact.source_document_id)
        approved_fact = ExtractedFact(
            field_name=fact.field_name,
            value=final_value,
            confidence=fact.confidence,
            source_quote=fact.source_quote,
        )
        written = _merge_field_facts(
            db,
            patient=patient,
            document=document,
            field_name=fact.field_name,
            facts=[approved_fact],
            extracted_at=fact.extracted_at,
        )
        fact.resulting_profile_field_id = written[0].id if written else None

    db.commit()

    from app.documents.commands import maybe_trigger_deferred_rag_indexing

    maybe_trigger_deferred_rag_indexing(db, document_id=fact.source_document_id)
    return fact


def reject_pending_fact(
    db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID, fact_id: uuid.UUID
) -> PendingProfileFact:
    """Rejects a staged fact — never merged, kept for audit. For
    OVERWRITE-strategy fields this may still trigger the batch's atomic
    merge (of whichever siblings were approved) if this was the last
    pending row in the batch — see _maybe_finalize_overwrite_batch.
    """
    fact = _get_owned_pending_fact(
        db, patient_id=patient_id, therapist_id=therapist_id, fact_id=fact_id
    )
    if fact.status != PENDING_STATUS_PENDING:
        raise PendingFactAlreadyResolved()

    fact.status = PENDING_STATUS_REJECTED
    fact.resolved_at = datetime.now(timezone.utc)
    fact.resolved_by_id = therapist_id

    strategy = FIELD_MERGE_STRATEGIES[fact.field_name]
    if strategy == STRATEGY_OVERWRITE:
        _maybe_finalize_overwrite_batch(db, fact)

    db.commit()

    from app.documents.commands import maybe_trigger_deferred_rag_indexing

    maybe_trigger_deferred_rag_indexing(db, document_id=fact.source_document_id)
    return fact


def _maybe_finalize_overwrite_batch(db: Session, fact: PendingProfileFact) -> None:
    """Called after marking one OVERWRITE-field pending row approved or
    rejected. If any sibling in the same (document, field) batch is still
    pending, does nothing yet. Once every row in the batch has a decision,
    merges every *approved* row's resolved value together as one atomic
    ProfileFieldsMerged event — mirroring the original synchronous
    all-at-once behavior — skipping the merge entirely if nothing in the
    batch was approved, so a fully-rejected batch leaves any prior active
    values for that field untouched rather than superseding them with
    nothing.
    """
    db.flush()
    batch = list(
        db.execute(
            select(PendingProfileFact).where(
                PendingProfileFact.source_document_id == fact.source_document_id,
                PendingProfileFact.field_name == fact.field_name,
            )
        ).scalars()
    )
    if any(row.status == PENDING_STATUS_PENDING for row in batch):
        return

    approved_rows = [row for row in batch if row.status == PENDING_STATUS_APPROVED]
    if not approved_rows:
        return

    patient = db.get(Patient, fact.patient_id)
    document = db.get(Document, fact.source_document_id)
    approved_facts = [
        ExtractedFact(
            field_name=row.field_name,
            value=row.resolved_value,
            confidence=row.confidence,
            source_quote=row.source_quote,
        )
        for row in approved_rows
    ]
    written = _merge_field_facts(
        db,
        patient=patient,
        document=document,
        field_name=fact.field_name,
        facts=approved_facts,
        extracted_at=fact.extracted_at,
    )
    for row, written_row in zip(approved_rows, written):
        row.resulting_profile_field_id = written_row.id

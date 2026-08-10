import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.briefs import projector
from app.briefs.events import BRIEF_GENERATED, STREAM_TYPE_BRIEF
from app.briefs.models import Brief
from app.core.llm_client import embed_text, generate_brief_text
from app.event_store.store import append_event
from app.patients.models import Patient
from app.profile import derived
from app.query_api import therapist as therapist_queries
from app.timeline.models import (
    ENTRY_TYPE_DOCUMENT_EXTRACTED,
    ENTRY_TYPE_MILESTONE,
    ENTRY_TYPE_PHASE_ADVANCE,
)


class PatientNotFound(Exception):
    pass


def _get_owned_patient(db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.therapist_id == therapist_id)
    ).scalar_one_or_none()
    if patient is None:
        raise PatientNotFound()
    return patient


def _get_latest_brief_row(
    db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID
) -> Brief | None:
    return db.execute(
        select(Brief)
        .where(Brief.patient_id == patient_id, Brief.therapist_id == therapist_id)
        .order_by(Brief.generated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_latest_brief(
    db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID
) -> Brief | None:
    """Read-only lookup of the most recently generated brief, with no LLM
    call — this is the "cache read" the patient-detail page uses to show a
    brief automatically without regenerating one on every visit. `None`
    means no brief has ever been generated for this patient, not an error.
    """
    _get_owned_patient(db, patient_id=patient_id, therapist_id=therapist_id)
    return _get_latest_brief_row(db, patient_id=patient_id, therapist_id=therapist_id)


def generate_brief(db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID) -> Brief:
    """Assembles a therapist prep brief (PRD Week 4 / M8): Knowledge Profile
    + events since the last brief + relevant RAG context, narrated into
    "since last visit" and "suggested focus" sections by one LLM call.
    Flags are never LLM-generated — they're the same typed, deterministic
    reasons used elsewhere in the Knowledge Profile (PRD §6.3).
    """
    patient = _get_owned_patient(db, patient_id=patient_id, therapist_id=therapist_id)

    last_brief = _get_latest_brief_row(db, patient_id=patient_id, therapist_id=therapist_id)
    since = last_brief.generated_at if last_brief is not None else patient.created_at

    profile_fields = therapist_queries.list_profile_fields(
        db, therapist_id=therapist_id, patient_id=patient_id
    )
    checkins = therapist_queries.list_checkins(db, therapist_id=therapist_id, patient_id=patient_id)

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=derived.ADHERENCE_WINDOW_DAYS)
    recent_checkin_count = sum(1 for c in checkins if c.submitted_at >= window_start)
    flags = derived.compute_needs_review_reasons(
        has_pending_extraction=therapist_queries.has_pending_facts(
            db, therapist_id=therapist_id, patient_id=patient_id
        ),
        has_recent_assistant_redirect=therapist_queries.has_recent_assistant_redirect(
            db, therapist_id=therapist_id, patient_id=patient_id, window_start=window_start
        ),
        invite_accepted_at=patient.invite_accepted_at,
        is_discharged=patient.current_phase == therapist_queries.DISCHARGED_PHASE,
        recent_checkin_count=recent_checkin_count,
        now=now,
    )
    pain_trend = derived.compute_pain_trend([(c.submitted_at, c.pain_level) for c in checkins])
    if pain_trend == derived.PAIN_TREND_WORSENING:
        flags.append("Pain trend: worsening")

    recent_events_summary = _summarize_recent_events(
        db, therapist_id=therapist_id, patient_id=patient_id, since=since
    )

    active_restrictions = therapist_queries.current_field_values(profile_fields, "active_restrictions")
    active_concerns = therapist_queries.current_field_values(profile_fields, "active_concerns")
    milestones = therapist_queries.current_field_values(profile_fields, "milestones")
    profile_summary = (
        f"Injury: {patient.injury}\n"
        f"Current phase: {patient.current_phase}\n"
        f"Active restrictions: {'; '.join(active_restrictions) or 'none'}\n"
        f"Active concerns: {'; '.join(active_concerns) or 'none'}\n"
        f"Milestones: {'; '.join(milestones) or 'none'}"
    )

    query_text = " ".join(
        [patient.injury, patient.current_phase, *active_concerns, *active_restrictions, *milestones]
    ).strip()
    query_embedding = embed_text(query_text, task_type="RETRIEVAL_QUERY")
    rag_chunks = therapist_queries.retrieve_patient_notes_chunks(
        db, therapist_id=therapist_id, patient_id=patient_id, query_embedding=query_embedding
    )
    note_excerpts = [chunk.chunk_text for chunk in rag_chunks]

    sections = generate_brief_text(
        profile_summary=profile_summary,
        flags=flags,
        recent_events_summary=recent_events_summary,
        note_excerpts=note_excerpts,
    )

    event = append_event(
        db,
        stream_id=uuid.uuid4(),
        stream_type=STREAM_TYPE_BRIEF,
        event_type=BRIEF_GENERATED,
        payload={
            "patient_id": str(patient_id),
            "therapist_id": str(therapist_id),
            "since_last_visit": sections.since_last_visit,
            "flags": flags,
            "suggested_focus": sections.suggested_focus,
            "generated_at": now.isoformat(),
        },
        actor_id=therapist_id,
        actor_role="therapist",
    )
    brief = projector.apply(db, event)
    db.commit()
    return brief


def _summarize_recent_events(
    db: Session, *, therapist_id: uuid.UUID, patient_id: uuid.UUID, since: datetime
) -> str:
    """"Since last visit" narration sourced from the Patient Timeline
    projector's read model — the single source of truth for chronological
    patient events — rather than re-deriving it from the event store.
    """
    entries = therapist_queries.list_timeline_entries(
        db, therapist_id=therapist_id, patient_id=patient_id
    )

    lines: list[str] = []
    for entry in entries:
        if entry.occurred_at <= since:
            continue
        if entry.entry_type == ENTRY_TYPE_PHASE_ADVANCE:
            note = f" ({entry.detail['note']})" if entry.detail.get("note") else ""
            lines.append(
                f"Phase advanced from {entry.detail['from_phase']} to {entry.detail['to_phase']}{note}."
            )
        elif entry.entry_type == ENTRY_TYPE_MILESTONE:
            lines.append(f"New milestone noted: {entry.detail['value']}.")
        elif entry.entry_type == ENTRY_TYPE_DOCUMENT_EXTRACTED:
            lines.append(f"Document '{entry.detail['filename']}' processed and extracted.")

    if not lines:
        return "No new activity recorded since the last visit."
    return "\n".join(f"- {line}" for line in lines)

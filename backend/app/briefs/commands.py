import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.briefs import projector
from app.briefs.events import BRIEF_GENERATED, STREAM_TYPE_BRIEF
from app.briefs.models import Brief
from app.core.llm_client import embed_text, generate_brief_text
from app.event_store.store import append_event, get_stream_events
from app.patients.events import PATIENT_PHASE_ADVANCED
from app.patients.models import Patient
from app.profile import derived
from app.profile.models import ProfileField
from app.query_api import therapist as therapist_queries


class PatientNotFound(Exception):
    pass


def generate_brief(db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID) -> Brief:
    """Assembles a therapist prep brief (PRD Week 4 / M8): Knowledge Profile
    + events since the last brief + relevant RAG context, narrated into
    "since last visit" and "suggested focus" sections by one LLM call.
    Flags are never LLM-generated — they're the same typed, deterministic
    reasons used elsewhere in the Knowledge Profile (PRD §6.3).
    """
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.therapist_id == therapist_id)
    ).scalar_one_or_none()
    if patient is None:
        raise PatientNotFound()

    last_brief = db.execute(
        select(Brief)
        .where(Brief.patient_id == patient_id, Brief.therapist_id == therapist_id)
        .order_by(Brief.generated_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    since = last_brief.generated_at if last_brief is not None else patient.created_at

    profile_fields = therapist_queries.list_profile_fields(
        db, therapist_id=therapist_id, patient_id=patient_id
    )
    checkins = therapist_queries.list_checkins(db, therapist_id=therapist_id, patient_id=patient_id)
    documents = therapist_queries.list_documents(db, therapist_id=therapist_id, patient_id=patient_id)

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=derived.ADHERENCE_WINDOW_DAYS)
    recent_checkin_count = sum(1 for c in checkins if c.submitted_at >= window_start)
    flags = derived.compute_needs_review_reasons(
        has_contradiction=any(f.is_contradiction for f in profile_fields),
        invite_accepted_at=patient.invite_accepted_at,
        is_discharged=patient.current_phase == therapist_queries.DISCHARGED_PHASE,
        recent_checkin_count=recent_checkin_count,
        now=now,
    )
    pain_trend = derived.compute_pain_trend([(c.submitted_at, c.pain_level) for c in checkins])
    if pain_trend == derived.PAIN_TREND_WORSENING:
        flags.append("Pain trend: worsening")

    recent_events_summary = _summarize_recent_events(
        db, patient=patient, profile_fields=profile_fields, documents=documents, since=since
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
    db: Session,
    *,
    patient: Patient,
    profile_fields: list[ProfileField],
    documents: list,
    since: datetime,
) -> str:
    """Small ad hoc "recent activity" query directly over the event store
    and existing read models — a stand-in for the Patient Timeline
    projector, which doesn't exist yet. Revisit once that projector lands.
    """
    lines: list[str] = []

    phase_events = [
        event
        for event in get_stream_events(db, stream_id=patient.id)
        if event.event_type == PATIENT_PHASE_ADVANCED and event.created_at > since
    ]
    for event in phase_events:
        note = f" ({event.payload['note']})" if event.payload.get("note") else ""
        lines.append(
            f"Phase advanced from {event.payload['from_phase']} to {event.payload['to_phase']}{note}."
        )

    for field in profile_fields:
        if field.extracted_at > since:
            lines.append(f"New {field.field_name.replace('_', ' ')} noted: {field.value}.")

    for document in documents:
        if document.extracted_at is not None and document.extracted_at > since:
            lines.append(f"Document '{document.filename}' processed and extracted.")

    if not lines:
        return "No new activity recorded since the last visit."
    return "\n".join(f"- {line}" for line in lines)

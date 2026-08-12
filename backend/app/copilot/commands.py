import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.copilot import projector
from app.copilot.events import (
    COPILOT_MESSAGE_POSTED,
    ROLE_ASSISTANT,
    ROLE_THERAPIST,
    STREAM_TYPE_COPILOT_MESSAGE,
)
from app.copilot.models import CopilotMessage
from app.core.llm_client import answer_copilot_message, embed_text
from app.event_store.store import append_event
from app.patients.models import Patient
from app.query_api import therapist as therapist_queries
from app.timeline.models import (
    ENTRY_TYPE_DOCUMENT_EXTRACTED,
    ENTRY_TYPE_MILESTONE,
    ENTRY_TYPE_PHASE_ADVANCE,
)

HISTORY_LIMIT = 10


class PatientNotFound(Exception):
    pass


def _get_owned_patient(db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.therapist_id == therapist_id)
    ).scalar_one_or_none()
    if patient is None:
        raise PatientNotFound()
    return patient


def list_messages(
    db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID
) -> list[CopilotMessage]:
    _get_owned_patient(db, patient_id=patient_id, therapist_id=therapist_id)
    return list(
        db.execute(
            select(CopilotMessage)
            .where(
                CopilotMessage.patient_id == patient_id,
                CopilotMessage.therapist_id == therapist_id,
            )
            .order_by(CopilotMessage.posted_at)
        ).scalars()
    )


def send_message(
    db: Session, *, patient_id: uuid.UUID, therapist_id: uuid.UUID, content: str
) -> CopilotMessage:
    """Posts one therapist message to the running copilot thread for this
    patient and returns the AI's grounded reply. Grounding mirrors what
    `briefs.commands.generate_brief` assembles (Knowledge Profile, recent
    activity, patient notes) plus the shared clinical-guidelines RAG corpus,
    and includes the last few turns of the conversation so follow-up
    questions stay coherent.
    """
    patient = _get_owned_patient(db, patient_id=patient_id, therapist_id=therapist_id)

    prior_messages = list_messages(db, patient_id=patient_id, therapist_id=therapist_id)
    history = [
        {"role": "user" if m.role == ROLE_THERAPIST else "assistant", "content": m.content}
        for m in prior_messages[-HISTORY_LIMIT:]
    ]

    now = datetime.now(timezone.utc)
    _append_message(
        db, patient_id=patient_id, therapist_id=therapist_id, role=ROLE_THERAPIST,
        content=content, posted_at=now,
    )

    profile_fields = therapist_queries.list_profile_fields(
        db, therapist_id=therapist_id, patient_id=patient_id
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

    recent_activity_summary = _summarize_recent_activity(
        db, therapist_id=therapist_id, patient_id=patient_id
    )

    query_embedding = embed_text(content, task_type="RETRIEVAL_QUERY", source="copilot")
    note_chunks = therapist_queries.retrieve_patient_notes_chunks(
        db, therapist_id=therapist_id, patient_id=patient_id, query_embedding=query_embedding
    )
    guideline_chunks = therapist_queries.retrieve_clinical_guideline_chunks(
        db, query_embedding=query_embedding
    )

    result = answer_copilot_message(
        question=content,
        profile_summary=profile_summary,
        recent_activity_summary=recent_activity_summary,
        patient_note_excerpts=[chunk.chunk_text for chunk in note_chunks],
        guideline_excerpts=[chunk.chunk_text for chunk in guideline_chunks],
        history=history,
    )

    reply = _append_message(
        db, patient_id=patient_id, therapist_id=therapist_id, role=ROLE_ASSISTANT,
        content=result.answer, posted_at=datetime.now(timezone.utc),
    )
    db.commit()
    return reply


def _append_message(
    db: Session,
    *,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    role: str,
    content: str,
    posted_at: datetime,
) -> CopilotMessage:
    event = append_event(
        db,
        stream_id=uuid.uuid4(),
        stream_type=STREAM_TYPE_COPILOT_MESSAGE,
        event_type=COPILOT_MESSAGE_POSTED,
        payload={
            "patient_id": str(patient_id),
            "therapist_id": str(therapist_id),
            "role": role,
            "content": content,
            "posted_at": posted_at.isoformat(),
        },
        actor_id=therapist_id,
        actor_role="therapist",
    )
    return projector.apply(db, event)


def _summarize_recent_activity(
    db: Session, *, therapist_id: uuid.UUID, patient_id: uuid.UUID
) -> str:
    """A general "what's happened recently" narration sourced from the
    Patient Timeline read model, independent of `briefs`' "since last
    brief" windowing — the copilot chat has no brief-generation cadence to
    anchor to, so it just surfaces the most recent entries.
    """
    entries = therapist_queries.list_timeline_entries(
        db, therapist_id=therapist_id, patient_id=patient_id
    )

    lines: list[str] = []
    for entry in entries[-10:]:
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
        return "No recent activity recorded."
    return "\n".join(f"- {line}" for line in lines)

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.assistant import projector
from app.assistant.events import ASSISTANT_QUESTION_ANSWERED, STREAM_TYPE_ASSISTANT_INTERACTION
from app.assistant.models import AssistantInteraction
from app.assistant.urgent_detection import detect_symptom_or_urgent
from app.core.llm_client import answer_patient_question, embed_text
from app.event_store.store import append_event
from app.patients.models import Patient
from app.query_api import patient as patient_queries

CLINIC_REDIRECT_MESSAGE = (
    "This assistant can share general recovery information, but it can't evaluate your "
    "specific symptoms or tell you whether something is serious. Please contact your clinic "
    "directly so a member of your care team can help."
)


class PatientNotFound(Exception):
    pass


def ask_assistant(db: Session, *, patient_id: uuid.UUID, question: str) -> AssistantInteraction:
    """Answers a single patient question against the shared patient-education
    RAG corpus (PRD §5.8/§9). Any symptom-related or urgent-sounding
    question is redirected to the clinic instead of answered — the
    deterministic keyword gate below is the authoritative check; the LLM's
    own `redirect` flag is only a defense-in-depth backstop, never the
    primary safety mechanism (PRD §6.5 — this split is structural, not a
    prompt-level convention).
    """
    if db.get(Patient, patient_id) is None:
        raise PatientNotFound()

    now = datetime.now(timezone.utc)

    if detect_symptom_or_urgent(question) is not None:
        answer = CLINIC_REDIRECT_MESSAGE
        redirected = True
    else:
        query_embedding = embed_text(question, task_type="RETRIEVAL_QUERY")
        chunks = patient_queries.retrieve_patient_education_chunks(
            db, query_embedding=query_embedding
        )
        education_excerpts = [chunk.chunk_text for chunk in chunks]
        result = answer_patient_question(question=question, education_excerpts=education_excerpts)
        if result.redirect:
            answer = CLINIC_REDIRECT_MESSAGE
            redirected = True
        else:
            answer = result.answer
            redirected = False

    event = append_event(
        db,
        stream_id=uuid.uuid4(),
        stream_type=STREAM_TYPE_ASSISTANT_INTERACTION,
        event_type=ASSISTANT_QUESTION_ANSWERED,
        payload={
            "patient_id": str(patient_id),
            "question": question,
            "answer": answer,
            "redirected": redirected,
            "asked_at": now.isoformat(),
        },
        actor_id=patient_id,
        actor_role="patient",
    )
    interaction = projector.apply(db, event)
    db.commit()
    return interaction

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.assistant.events import ASSISTANT_QUESTION_ANSWERED
from app.assistant.models import AssistantInteraction
from app.event_store.models import Event


def apply(db: Session, event: Event) -> AssistantInteraction | None:
    """Applies one event to the assistant read model. Called synchronously
    right after the causing event is appended, and (eventually) by full
    replay.
    """
    if event.event_type == ASSISTANT_QUESTION_ANSWERED:
        return _apply_assistant_question_answered(db, event)
    return None


def _apply_assistant_question_answered(db: Session, event: Event) -> AssistantInteraction:
    payload = event.payload
    interaction = AssistantInteraction(
        id=event.stream_id,
        patient_id=uuid.UUID(payload["patient_id"]),
        question=payload["question"],
        answer=payload["answer"],
        redirected=payload["redirected"],
        asked_at=datetime.fromisoformat(payload["asked_at"]),
    )
    db.add(interaction)
    db.flush()
    return interaction

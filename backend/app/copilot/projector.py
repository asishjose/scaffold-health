import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.copilot.events import COPILOT_MESSAGE_POSTED
from app.copilot.models import CopilotMessage
from app.event_store.models import Event


def apply(db: Session, event: Event) -> CopilotMessage | None:
    """Applies one event to the copilot read model. Called synchronously
    right after the causing event is appended, and (eventually) by full
    replay.
    """
    if event.event_type == COPILOT_MESSAGE_POSTED:
        return _apply_copilot_message_posted(db, event)
    return None


def _apply_copilot_message_posted(db: Session, event: Event) -> CopilotMessage:
    payload = event.payload
    message = CopilotMessage(
        id=event.stream_id,
        patient_id=uuid.UUID(payload["patient_id"]),
        therapist_id=uuid.UUID(payload["therapist_id"]),
        role=payload["role"],
        content=payload["content"],
        posted_at=datetime.fromisoformat(payload["posted_at"]),
    )
    db.add(message)
    db.flush()
    return message

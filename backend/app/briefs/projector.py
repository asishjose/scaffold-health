import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.briefs.events import BRIEF_GENERATED
from app.briefs.models import Brief
from app.event_store.models import Event


def apply(db: Session, event: Event) -> Brief | None:
    """Applies one event to the briefs read model. Called synchronously
    right after the causing event is appended, and (eventually) by full
    replay.
    """
    if event.event_type == BRIEF_GENERATED:
        return _apply_brief_generated(db, event)
    return None


def _apply_brief_generated(db: Session, event: Event) -> Brief:
    payload = event.payload
    brief = Brief(
        id=event.stream_id,
        patient_id=uuid.UUID(payload["patient_id"]),
        therapist_id=uuid.UUID(payload["therapist_id"]),
        since_last_visit=payload["since_last_visit"],
        flags=payload["flags"],
        suggested_focus=payload["suggested_focus"],
        generated_at=datetime.fromisoformat(payload["generated_at"]),
    )
    db.add(brief)
    db.flush()
    return brief

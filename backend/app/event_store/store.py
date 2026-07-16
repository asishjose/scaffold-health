import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.event_store.models import Event


def append_event(
    db: Session,
    *,
    stream_id: uuid.UUID,
    stream_type: str,
    event_type: str,
    payload: dict,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    idempotency_key: str | None = None,
) -> Event:
    """The only write entry point to the event store. Command handlers call
    this and nothing else — no direct writes to read models.

    Concurrent appends to the same stream are serialized with a Postgres
    advisory lock keyed by stream_id, so stream_version stays gap-free and
    monotonic even under concurrent requests.
    """
    if idempotency_key is not None:
        existing = db.execute(
            select(Event).where(Event.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(stream_id)})

    next_version = (
        db.execute(
            select(Event.stream_version)
            .where(Event.stream_id == stream_id)
            .order_by(Event.stream_version.desc())
            .limit(1)
        ).scalar_one_or_none()
        or 0
    ) + 1

    event = Event(
        stream_id=stream_id,
        stream_type=stream_type,
        stream_version=next_version,
        event_type=event_type,
        payload=payload,
        actor_id=actor_id,
        actor_role=actor_role,
        idempotency_key=idempotency_key,
    )
    db.add(event)
    db.flush()
    return event


def get_stream_events(db: Session, *, stream_id: uuid.UUID) -> list[Event]:
    """All events for one stream, in version order. Used by per-stream
    replay and by command handlers that need a stream's current state.
    """
    return list(
        db.execute(
            select(Event).where(Event.stream_id == stream_id).order_by(Event.stream_version)
        ).scalars()
    )


def get_all_events(db: Session) -> list[Event]:
    """Every event ever appended, in global append order. Used by full
    projection replay (projectors/replay.py).
    """
    return list(db.execute(select(Event).order_by(Event.created_at, Event.id)).scalars())

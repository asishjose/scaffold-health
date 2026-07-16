import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.event_store.store import append_event, get_all_events, get_stream_events


def test_append_event_assigns_monotonic_versions(db: Session) -> None:
    stream_id = uuid.uuid4()

    first = append_event(
        db, stream_id=stream_id, stream_type="test", event_type="Thing1", payload={"n": 1}
    )
    second = append_event(
        db, stream_id=stream_id, stream_type="test", event_type="Thing2", payload={"n": 2}
    )
    third = append_event(
        db, stream_id=stream_id, stream_type="test", event_type="Thing3", payload={"n": 3}
    )
    db.commit()

    assert (first.stream_version, second.stream_version, third.stream_version) == (1, 2, 3)


def test_append_event_versions_are_independent_per_stream(db: Session) -> None:
    stream_a = uuid.uuid4()
    stream_b = uuid.uuid4()

    a1 = append_event(db, stream_id=stream_a, stream_type="test", event_type="E", payload={})
    b1 = append_event(db, stream_id=stream_b, stream_type="test", event_type="E", payload={})
    a2 = append_event(db, stream_id=stream_a, stream_type="test", event_type="E", payload={})
    db.commit()

    assert (a1.stream_version, b1.stream_version, a2.stream_version) == (1, 1, 2)


def test_append_event_is_idempotent(db: Session) -> None:
    stream_id = uuid.uuid4()
    key = str(uuid.uuid4())

    first = append_event(
        db,
        stream_id=stream_id,
        stream_type="test",
        event_type="E",
        payload={"attempt": 1},
        idempotency_key=key,
    )
    db.commit()

    second = append_event(
        db,
        stream_id=stream_id,
        stream_type="test",
        event_type="E",
        payload={"attempt": 2},
        idempotency_key=key,
    )
    db.commit()

    assert second.id == first.id
    assert second.payload == {"attempt": 1}
    assert len(get_stream_events(db, stream_id=stream_id)) == 1


def test_get_stream_events_returns_version_order(db: Session) -> None:
    stream_id = uuid.uuid4()
    for i in range(5):
        append_event(
            db, stream_id=stream_id, stream_type="test", event_type="E", payload={"i": i}
        )
    db.commit()

    events = get_stream_events(db, stream_id=stream_id)
    assert [e.payload["i"] for e in events] == [0, 1, 2, 3, 4]


def test_get_all_events_includes_multiple_streams(db: Session) -> None:
    stream_a, stream_b = uuid.uuid4(), uuid.uuid4()
    append_event(db, stream_id=stream_a, stream_type="test", event_type="E", payload={})
    append_event(db, stream_id=stream_b, stream_type="test", event_type="E", payload={})
    db.commit()

    all_ids = {e.stream_id for e in get_all_events(db)}
    assert {stream_a, stream_b} <= all_ids


def test_events_table_rejects_update(db: Session) -> None:
    stream_id = uuid.uuid4()
    event = append_event(
        db, stream_id=stream_id, stream_type="test", event_type="E", payload={"v": 1}
    )
    db.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(
            text("UPDATE events SET payload = '{}' WHERE id = :id"), {"id": str(event.id)}
        )
        db.flush()
    db.rollback()


def test_events_table_rejects_delete(db: Session) -> None:
    stream_id = uuid.uuid4()
    event = append_event(db, stream_id=stream_id, stream_type="test", event_type="E", payload={})
    db.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM events WHERE id = :id"), {"id": str(event.id)})
        db.flush()
    db.rollback()


def test_events_table_rejects_truncate(db: Session) -> None:
    stream_id = uuid.uuid4()
    append_event(db, stream_id=stream_id, stream_type="test", event_type="E", payload={})
    db.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("TRUNCATE events"))
        db.flush()
    db.rollback()

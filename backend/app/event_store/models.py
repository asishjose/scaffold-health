import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Event(Base):
    """Append-only log of every command that has ever succeeded. The sole
    source of truth — all read models (Knowledge Profile, Timeline, RAG
    indexes) are disposable projections derived from this table.
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("stream_id", "stream_version", name="uq_events_stream_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    stream_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stream_version: Mapped[int] = mapped_column(Integer, nullable=False)

    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)

    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

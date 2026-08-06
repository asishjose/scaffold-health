import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.copilot.events import ROLE_ASSISTANT, ROLE_THERAPIST
from app.core.db import Base


class CopilotMessage(Base):
    """Read model projected from `CopilotMessagePosted` events — one row per
    message in a therapist's running copilot conversation about one patient.
    There is no separate "session" entity: the (patient_id, therapist_id)
    pair is the thread. Never written to directly; only by the copilot
    projector.
    """

    __tablename__ = "copilot_messages"
    __table_args__ = (
        CheckConstraint(
            f"role IN ('{ROLE_THERAPIST}', '{ROLE_ASSISTANT}')", name="ck_copilot_messages_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.id"), nullable=False, index=True
    )

    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

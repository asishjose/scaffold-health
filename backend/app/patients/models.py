import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Patient(Base):
    """Read model projected from `PatientCreated` / `PatientAccountActivated`
    events. Never written to directly by request handlers — only by the
    patients projector.
    """

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Fixed to ACL reconstruction for MVP; immutable once set.
    injury: Mapped[str] = mapped_column(String(64), nullable=False)
    surgery_date: Mapped[date] = mapped_column(Date, nullable=False)

    current_phase: Mapped[str] = mapped_column(String(64), nullable=False)

    invite_token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    invite_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invite_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

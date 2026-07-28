import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.checkins.schemas import CheckInResponse
from app.profile.schemas import ProfileFieldResponse


class PatientIntakeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    date_of_birth: date
    contact_email: EmailStr
    surgery_date: date

    @field_validator("date_of_birth")
    @classmethod
    def date_of_birth_must_be_past(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("date_of_birth must be in the past")
        return value


class PatientIntakeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    invite_token: str
    invite_expires_at: datetime


class PatientListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    current_phase: str
    surgery_date: date
    invite_accepted_at: datetime | None
    needs_review: list[str] = Field(default_factory=list)


class PatientDetailResponse(BaseModel):
    """Full therapist-facing view."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    therapist_id: uuid.UUID
    name: str
    date_of_birth: date
    contact_email: str
    injury: str
    surgery_date: date
    current_phase: str
    invite_accepted_at: datetime | None
    created_at: datetime
    pain_history: list[CheckInResponse] = Field(default_factory=list)
    active_restrictions: list[str] = Field(default_factory=list)
    active_concerns: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    pain_trend: str | None = None
    exercise_adherence: float | None = None
    needs_review: list[str] = Field(default_factory=list)
    profile_fields: list[ProfileFieldResponse] = Field(default_factory=list)


class AdvancePhaseRequest(BaseModel):
    target_phase: str
    note: str | None = Field(default=None, max_length=2000)


class PhaseAdvanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    current_phase: str


class PatientPortalDetailResponse(BaseModel):
    """Reduced patient-facing view: no therapist/provenance/invite data."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    injury: str
    surgery_date: date
    current_phase: str
    pain_trend: str | None = None

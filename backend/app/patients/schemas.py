import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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


class PatientPortalDetailResponse(BaseModel):
    """Reduced patient-facing view: no therapist/provenance/invite data."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    injury: str
    surgery_date: date
    current_phase: str

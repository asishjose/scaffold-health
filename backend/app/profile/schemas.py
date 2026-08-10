import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProfileFieldResponse(BaseModel):
    """One extracted fact, for the therapist provenance panel."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_name: str
    value: str
    confidence: float | None
    source_quote: str | None
    source_document_id: uuid.UUID | None
    extracted_at: datetime
    superseded_at: datetime | None


class PendingProfileFactResponse(BaseModel):
    """One staged fact awaiting therapist approval/rejection."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_name: str
    value: str
    confidence: float
    source_quote: str
    source_document_id: uuid.UUID
    extracted_at: datetime
    is_contradiction: bool
    is_low_confidence: bool
    status: str
    resolved_at: datetime | None
    resolved_value: str | None
    resulting_profile_field_id: uuid.UUID | None


class ResolvePendingFactRequest(BaseModel):
    value: str | None = None

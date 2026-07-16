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
    is_contradiction: bool
    superseded_at: datetime | None

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CheckInRequest(BaseModel):
    pain_level: int = Field(ge=0, le=10)
    note: str | None = Field(default=None, max_length=2000)


class CheckInResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pain_level: int
    note: str | None
    submitted_at: datetime

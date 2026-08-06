import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CopilotMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CopilotMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    role: str
    content: str
    posted_at: datetime

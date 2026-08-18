import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssistantQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AssistantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    question: str
    answer: str
    redirected: bool
    asked_at: datetime


class FlaggedQuestionResponse(BaseModel):
    """One redirected AssistantInteraction awaiting therapist acknowledgment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    question: str
    answer: str
    asked_at: datetime

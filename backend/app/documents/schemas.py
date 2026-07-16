import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    created_at: datetime


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    status: str
    created_at: datetime
    extracted_at: datetime | None

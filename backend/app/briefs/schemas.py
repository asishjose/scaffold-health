import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BriefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    since_last_visit: str
    flags: list[str]
    suggested_focus: str
    generated_at: datetime

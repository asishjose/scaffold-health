import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.briefs import commands
from app.briefs.schemas import BriefResponse
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/patients/{patient_id}/brief", tags=["briefs"])


@router.post("", response_model=BriefResponse, status_code=status.HTTP_201_CREATED)
def generate_brief(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefResponse:
    require_role(current_user, "therapist")

    try:
        brief = commands.generate_brief(db, patient_id=patient_id, therapist_id=current_user.id)
    except commands.PatientNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
        ) from exc

    return BriefResponse.model_validate(brief)

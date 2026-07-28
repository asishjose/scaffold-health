import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.checkins import commands
from app.checkins.schemas import CheckInRequest, CheckInResponse
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/patients/{patient_id}/checkins", tags=["checkins"])


@router.post("", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
def submit_checkin(
    patient_id: uuid.UUID,
    payload: CheckInRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckInResponse:
    require_role(current_user, "patient")
    if current_user.id != patient_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    try:
        checkin = commands.submit_checkin(
            db, patient_id=patient_id, pain_level=payload.pain_level, note=payload.note
        )
    except commands.PatientNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
        ) from exc

    return CheckInResponse.model_validate(checkin)

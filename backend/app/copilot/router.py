import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.copilot import commands
from app.copilot.schemas import CopilotMessageRequest, CopilotMessageResponse
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/patients/{patient_id}/copilot/messages", tags=["copilot"])


@router.get("", response_model=list[CopilotMessageResponse])
def list_messages(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CopilotMessageResponse]:
    require_role(current_user, "therapist")

    try:
        messages = commands.list_messages(db, patient_id=patient_id, therapist_id=current_user.id)
    except commands.PatientNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
        ) from exc

    return [CopilotMessageResponse.model_validate(message) for message in messages]


@router.post("", response_model=CopilotMessageResponse, status_code=status.HTTP_201_CREATED)
def post_message(
    patient_id: uuid.UUID,
    payload: CopilotMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CopilotMessageResponse:
    require_role(current_user, "therapist")

    try:
        message = commands.send_message(
            db, patient_id=patient_id, therapist_id=current_user.id, content=payload.content
        )
    except commands.PatientNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
        ) from exc

    return CopilotMessageResponse.model_validate(message)

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.assistant import commands
from app.assistant.schemas import AssistantQuestionRequest, AssistantResponse
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/patients/{patient_id}/assistant", tags=["assistant"])


@router.post("", response_model=AssistantResponse, status_code=status.HTTP_201_CREATED)
def ask_assistant(
    patient_id: uuid.UUID,
    payload: AssistantQuestionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantResponse:
    require_role(current_user, "patient")
    if current_user.id != patient_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    try:
        interaction = commands.ask_assistant(db, patient_id=patient_id, question=payload.question)
    except commands.PatientNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
        ) from exc

    return AssistantResponse.model_validate(interaction)

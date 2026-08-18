import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.assistant import commands
from app.assistant.models import AssistantInteraction
from app.assistant.schemas import AssistantQuestionRequest, AssistantResponse, FlaggedQuestionResponse
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user, require_role
from app.query_api import therapist as therapist_queries

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


@router.get("/flagged-questions", response_model=list[FlaggedQuestionResponse])
def list_flagged_questions(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FlaggedQuestionResponse]:
    require_role(current_user, "therapist")

    patient = therapist_queries.get_patient_detail(
        db, therapist_id=current_user.id, patient_id=patient_id
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    interactions = therapist_queries.list_flagged_questions(
        db, therapist_id=current_user.id, patient_id=patient_id
    )
    return [FlaggedQuestionResponse.model_validate(i) for i in interactions]


@router.post(
    "/flagged-questions/{interaction_id}/acknowledge", response_model=FlaggedQuestionResponse
)
def acknowledge_flagged_question(
    patient_id: uuid.UUID,
    interaction_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FlaggedQuestionResponse:
    require_role(current_user, "therapist")

    try:
        commands.acknowledge_flagged_question(
            db, patient_id=patient_id, therapist_id=current_user.id, interaction_id=interaction_id
        )
    except commands.FlaggedQuestionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flagged question not found"
        ) from exc
    except commands.FlaggedQuestionAlreadyAcknowledged as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already acknowledged"
        ) from exc

    interaction = db.get(AssistantInteraction, interaction_id)
    return FlaggedQuestionResponse.model_validate(interaction)

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user, require_role
from app.checkins.schemas import CheckInResponse
from app.patients import commands
from app.patients.schemas import (
    AdvancePhaseRequest,
    PatientDetailResponse,
    PatientIntakeRequest,
    PatientIntakeResponse,
    PatientListItem,
    PatientPortalDetailResponse,
    PhaseAdvanceResponse,
)
from app.query_api import patient as patient_queries
from app.query_api import therapist as therapist_queries

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientIntakeResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientIntakeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientIntakeResponse:
    require_role(current_user, "therapist")

    try:
        patient = commands.create_patient(
            db,
            therapist_id=current_user.id,
            name=payload.name,
            date_of_birth=payload.date_of_birth,
            contact_email=payload.contact_email,
            surgery_date=payload.surgery_date,
        )
    except commands.TherapistNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Therapist not found"
        ) from exc

    return PatientIntakeResponse.model_validate(patient)


@router.get("", response_model=list[PatientListItem])
def list_caseload(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PatientListItem]:
    require_role(current_user, "therapist")

    patients = therapist_queries.list_caseload(db, therapist_id=current_user.id)
    return [PatientListItem.model_validate(patient) for patient in patients]


@router.get("/{patient_id}", response_model=PatientDetailResponse | PatientPortalDetailResponse)
def get_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientDetailResponse | PatientPortalDetailResponse:
    require_role(current_user, "therapist", "patient")

    if current_user.role == "therapist":
        patient = therapist_queries.get_patient_detail(
            db, therapist_id=current_user.id, patient_id=patient_id
        )
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        checkins = therapist_queries.list_checkins(
            db, therapist_id=current_user.id, patient_id=patient_id
        )
        detail = PatientDetailResponse.model_validate(patient)
        return detail.model_copy(
            update={"pain_history": [CheckInResponse.model_validate(c) for c in checkins]}
        )

    if current_user.id != patient_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    patient = patient_queries.get_own_patient(db, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return PatientPortalDetailResponse.model_validate(patient)


@router.post("/{patient_id}/phase", response_model=PhaseAdvanceResponse)
def advance_phase(
    patient_id: uuid.UUID,
    payload: AdvancePhaseRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PhaseAdvanceResponse:
    require_role(current_user, "therapist")

    try:
        patient = commands.advance_phase(
            db,
            patient_id=patient_id,
            therapist_id=current_user.id,
            target_phase=payload.target_phase,
            note=payload.note,
        )
    except commands.PatientNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
        ) from exc
    except commands.InvalidPhaseTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invalid phase transition"
        ) from exc

    return PhaseAdvanceResponse.model_validate(patient)

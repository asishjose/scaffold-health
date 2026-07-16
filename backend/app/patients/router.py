import uuid
from datetime import datetime, timedelta, timezone

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
from app.profile import derived
from app.profile.schemas import ProfileFieldResponse
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
    reasons_by_patient = therapist_queries.list_needs_review_reasons(
        db, therapist_id=current_user.id, patients=patients
    )
    return [
        PatientListItem.model_validate(patient).model_copy(
            update={"needs_review": reasons_by_patient.get(patient.id, [])}
        )
        for patient in patients
    ]


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
        profile_fields = therapist_queries.list_profile_fields(
            db, therapist_id=current_user.id, patient_id=patient_id
        )

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=derived.ADHERENCE_WINDOW_DAYS)
        recent_checkin_count = sum(1 for c in checkins if c.submitted_at >= window_start)
        needs_review = derived.compute_needs_review_reasons(
            has_contradiction=any(f.is_contradiction for f in profile_fields),
            invite_accepted_at=patient.invite_accepted_at,
            is_discharged=patient.current_phase == therapist_queries.DISCHARGED_PHASE,
            recent_checkin_count=recent_checkin_count,
            now=now,
        )

        detail = PatientDetailResponse.model_validate(patient)
        return detail.model_copy(
            update={
                "pain_history": [CheckInResponse.model_validate(c) for c in checkins],
                "active_restrictions": therapist_queries.current_field_values(
                    profile_fields, "active_restrictions"
                ),
                "active_concerns": therapist_queries.current_field_values(
                    profile_fields, "active_concerns"
                ),
                "milestones": therapist_queries.current_field_values(profile_fields, "milestones"),
                "pain_trend": derived.compute_pain_trend(
                    [(c.submitted_at, c.pain_level) for c in checkins]
                ),
                "exercise_adherence": (
                    derived.compute_exercise_adherence(
                        [c.submitted_at for c in checkins], now=now
                    )
                    if patient.invite_accepted_at
                    else None
                ),
                "needs_review": needs_review,
                "profile_fields": [ProfileFieldResponse.model_validate(f) for f in profile_fields],
            }
        )

    if current_user.id != patient_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    patient = patient_queries.get_own_patient(db, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    checkins = patient_queries.list_own_checkins(db, patient_id=patient_id)
    portal = PatientPortalDetailResponse.model_validate(patient)
    return portal.model_copy(
        update={
            "pain_trend": derived.compute_pain_trend(
                [(c.submitted_at, c.pain_level) for c in checkins]
            ),
        }
    )


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

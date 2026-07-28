import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user, require_role
from app.query_api import patient as patient_queries
from app.query_api import therapist as therapist_queries
from app.timeline.schemas import (
    TimelineEntryResponse,
    TimelinePortalEntryResponse,
    build_timeline_entry_response,
    build_timeline_portal_entry_response,
)

router = APIRouter(prefix="/patients/{patient_id}/timeline", tags=["timeline"])


@router.get("", response_model=list[TimelineEntryResponse] | list[TimelinePortalEntryResponse])
def get_timeline(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TimelineEntryResponse] | list[TimelinePortalEntryResponse]:
    require_role(current_user, "therapist", "patient")

    if current_user.role == "therapist":
        patient = therapist_queries.get_patient_detail(
            db, therapist_id=current_user.id, patient_id=patient_id
        )
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        entries = therapist_queries.list_timeline_entries(
            db, therapist_id=current_user.id, patient_id=patient_id
        )
        return [build_timeline_entry_response(entry) for entry in entries]

    if current_user.id != patient_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    patient = patient_queries.get_own_patient(db, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    entries = patient_queries.list_own_timeline_entries(db, patient_id=patient_id)
    return [build_timeline_portal_entry_response(entry) for entry in entries]

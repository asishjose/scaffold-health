import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user, require_role
from app.documents import commands
from app.documents.schemas import DocumentListItem, DocumentUploadResponse
from app.query_api import therapist as therapist_queries

router = APIRouter(prefix="/patients/{patient_id}/documents", tags=["documents"])


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    patient_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    require_role(current_user, "therapist")

    file_bytes = await file.read()
    try:
        document = commands.upload_document(
            db,
            patient_id=patient_id,
            therapist_id=current_user.id,
            filename=file.filename or "upload.pdf",
            content_type=file.content_type or "application/octet-stream",
            file_bytes=file_bytes,
        )
    except commands.PatientNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
        ) from exc
    except commands.InvalidFileType as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported"
        ) from exc

    return DocumentUploadResponse.model_validate(document)


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentListItem]:
    require_role(current_user, "therapist")

    patient = therapist_queries.get_patient_detail(
        db, therapist_id=current_user.id, patient_id=patient_id
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    documents = therapist_queries.list_documents(
        db, therapist_id=current_user.id, patient_id=patient_id
    )
    return [DocumentListItem.model_validate(document) for document in documents]

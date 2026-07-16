from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import commands, service
from app.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    TherapistSignupRequest,
    TherapistSignupResponse,
    TokenResponse,
)
from app.core.db import get_db
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TherapistSignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: TherapistSignupRequest, db: Session = Depends(get_db)) -> TherapistSignupResponse:
    try:
        therapist = commands.register_therapist(
            db,
            name=payload.name,
            email=payload.email,
            password=payload.password,
            registration_code=payload.registration_code,
        )
    except commands.InvalidRegistrationCode as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid registration code"
        ) from exc
    except commands.EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc

    return TherapistSignupResponse(id=therapist.id, name=therapist.name, email=therapist.email)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    therapist = service.authenticate_therapist(db, email=payload.email, password=payload.password)
    if therapist is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )

    return TokenResponse(
        access_token=create_access_token(subject=str(therapist.id), role="therapist"),
        refresh_token=create_refresh_token(subject=str(therapist.id), role="therapist"),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(payload: RefreshRequest) -> AccessTokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type=TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    return AccessTokenResponse(
        access_token=create_access_token(subject=claims["sub"], role=claims["role"])
    )

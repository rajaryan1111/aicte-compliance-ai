"""Authentication endpoints: login and token issuance."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.core.security import (
    DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    verify_password,
)
from backend.app.db.models import User
from backend.app.db.session import get_db
from backend.app.repositories.user_repository import UserRepository
from backend.app.schemas.auth import LoginRequest, Token, UserRead

router = APIRouter()


@router.post(
    "/token",
    response_model=Token,
    summary="Issue JWT access token",
    description="Authenticate user with username and password, returning a signed JWT access token.",
)
def login_for_access_token(
    credentials: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Token:
    """Authenticate credentials and issue a signed JWT access token."""
    user = UserRepository.get_by_username(db, credentials.username)
    if user is None or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        subject=user.id,
        extra_claims={"username": user.username},
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current user profile",
)
def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    """Return profile details for the authenticated user."""
    return UserRead.model_validate(current_user)

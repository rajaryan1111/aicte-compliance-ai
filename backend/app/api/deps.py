"""FastAPI dependencies for authentication, database session, and tenant authorization."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from backend.app.core.rbac import has_permission
from backend.app.core.security import decode_access_token
from backend.app.db.models import InstitutionMembership, User
from backend.app.db.session import get_db
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.application_service import ApplicationService

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,
)

_application_service_instance = ApplicationService()


def get_application_service() -> ApplicationService:
    """Dependency providing singleton ApplicationService instance."""
    return _application_service_instance


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    """Validate Bearer token signature, expiry, and fetch active user from database.

    Returns 401 Unauthorized for missing, invalid, expired or inactive credentials.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token subject claim is missing.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = int(sub)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = UserRepository.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def verify_institution_membership(
    db: Session,
    user: User,
    institution_id: int,
    *,
    required_permission: str | None = None,
) -> InstitutionMembership:
    """Enforce server-side tenant isolation and role permissions.

    Conceals foreign/unauthorized tenant resources via 404 to prevent resource probing.
    Enforces role permissions via 403 Forbidden.
    """
    membership = UserRepository.get_membership(db, user.id, institution_id)
    if membership is None or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found or access denied.",
        )

    if required_permission is not None:
        if not has_permission(membership.role, required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Insufficient permissions for operation '{required_permission}'.",
            )

    return membership


def get_storage():
    """Dependency providing singleton storage backend."""
    from backend.app.core.storage import get_storage_backend
    return get_storage_backend()


def get_document_processing_service():
    """Dependency providing singleton DocumentProcessingService instance."""
    from backend.app.services.document_processing_service import DocumentProcessingService
    return DocumentProcessingService()


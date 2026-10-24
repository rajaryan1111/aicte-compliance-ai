"""Authenticated, tenant-scoped audit package generation, download, and verification endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, verify_institution_membership
from backend.app.core.rbac import (
    PERMISSION_AUDIT_PACKAGE_CREATE,
    PERMISSION_AUDIT_PACKAGE_READ,
)
from backend.app.db.models import Application, User
from backend.app.db.session import get_db
from backend.app.schemas.audit_package import (
    AuditPackageCreateRequest,
    AuditPackageDetailRead,
    AuditPackageListResponse,
    AuditPackageVerificationResponse,
)
from backend.app.services.audit_package_service import (
    AuditPackageNotFoundError,
    AuditPackageService,
)

router = APIRouter()


@router.post(
    "/applications/{application_id}/audit-packages",
    response_model=AuditPackageDetailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an exportable, tamper-evident audit package",
    description="Consolidates scrutiny report, findings resolution, immutable review history, audit trail, and evidence files into a cryptographically sealed ZIP archive.",
)
def create_audit_package_endpoint(
    application_id: int,
    payload: AuditPackageCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AuditPackageDetailRead:
    """Trigger creation of an audit package within the tenant boundary."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_AUDIT_PACKAGE_CREATE,
    )

    try:
        return AuditPackageService.create_package(
            db, application_id=application_id, user=current_user, payload=payload
        )
    except AuditPackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/applications/{application_id}/audit-packages",
    response_model=AuditPackageListResponse,
    summary="List generated audit packages for an application",
    description="Retrieve chronological list of exportable audit packages available for auditor hand-off.",
)
def list_audit_packages_endpoint(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Limit")] = 20,
) -> AuditPackageListResponse:
    """List audit packages scoped to the application."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_AUDIT_PACKAGE_READ,
    )

    return AuditPackageService.list_packages(db, application_id=application_id, skip=skip, limit=limit)


@router.get(
    "/applications/{application_id}/audit-packages/{package_id}",
    response_model=AuditPackageDetailRead,
    summary="Get audit package details and cryptographic manifest",
    description="Inspect package root hash, file checksums, and audit metadata.",
)
def get_audit_package_endpoint(
    application_id: int,
    package_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AuditPackageDetailRead:
    """Retrieve package details with cryptographic manifest."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_AUDIT_PACKAGE_READ,
    )

    try:
        return AuditPackageService.get_package(db, application_id=application_id, package_id=package_id)
    except AuditPackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/applications/{application_id}/audit-packages/{package_id}/download",
    summary="Download the sealed audit package archive",
    description="Download the complete ZIP archive containing reports, evidence manifests, and checksums.",
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "Sealed audit package ZIP file",
        }
    },
)
def download_audit_package_endpoint(
    application_id: int,
    package_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Download package archive as streaming binary."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_AUDIT_PACKAGE_READ,
    )

    try:
        zip_bytes, filename = AuditPackageService.get_package_download_bytes(
            db, application_id=application_id, package_id=package_id
        )
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AuditPackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/audit-packages/verify",
    response_model=AuditPackageVerificationResponse,
    summary="Verify cryptographic integrity of an exported audit package",
    description="Inspects ZIP archive, verifies SHA-256 checksum of every contained artifact against manifest, and validates the root digest.",
)
async def verify_audit_package_endpoint(
    file: Annotated[UploadFile, File(description="Audit package ZIP archive to verify")],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AuditPackageVerificationResponse:
    """Verify package archive integrity and report any tampering."""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    return AuditPackageService.verify_package_archive(file_bytes)

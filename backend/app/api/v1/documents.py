"""Authenticated, tenant-scoped document upload, private storage, and retrieval endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    get_application_service,
    get_current_user,
    get_storage,
    verify_institution_membership,
)
from backend.app.core.dispatcher import dispatch_outbox_message
from backend.app.core.rbac import (
    PERMISSION_APPLICATION_READ,
    PERMISSION_APPLICATION_UPDATE,
)
from backend.app.core.storage import StorageBackend, generate_storage_key
from backend.app.core.upload_validator import (
    FileTooLargeError,
    UploadValidationError,
    read_stream_bounded,
    validate_upload_bytes,
)
from backend.app.db.models import Application, Document, DocumentVersion, Finding, User
from backend.app.db.session import get_db
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.repositories.outbox_repository import OutboxRepository
from backend.app.repositories.processing_job_repository import ProcessingJobRepository
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentRead,
    DocumentUploadResponse,
    DocumentVersionRead,
    ProcessingJobRead,
    ProcessingJobStatusResponse,
)
from backend.app.services.application_service import ApplicationService

router = APIRouter()


@router.post(
    "/{application_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload document to application slot",
    description="Validate file, store in private quarantine, persist durable processing job, and dispatch to worker.",
)
def upload_application_document(
    application_id: int,
    document_type: Annotated[str, Form(description="Logical document slot identifier")],
    file: Annotated[UploadFile, File(description="Document payload (PDF, JPEG, PNG, TIFF, WEBP)")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[ApplicationService, Depends(get_application_service)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    response: Response,
    prefer: Annotated[str | None, Header(description="Async preference header")] = None,
) -> DocumentUploadResponse:
    """Secure document intake enforcing tenant boundary, durable job persistence, and worker dispatch."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    # Enforce tenant isolation & write permission
    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_UPDATE,
    )

    clean_type = document_type.strip()
    if not clean_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_type must be a non-empty string.",
        )

    # 1. Read bounded stream & perform file validation
    try:
        raw_bytes = read_stream_bounded(file.file)
        validated = validate_upload_bytes(
            raw_bytes,
            filename=file.filename,
            declared_content_type=file.content_type,
        )
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except UploadValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # 2. Private storage write under opaque server-side key (quarantine)
    file_ext = Path(validated.file_name).suffix
    storage_key = generate_storage_key(sha256=validated.sha256, extension=file_ext)
    storage.put(storage_key, validated.data)

    # 3. Create document version and durable processing job within single DB transaction
    try:
        doc, version = service.add_document_version(
            db,
            application_id=app.id,
            document_type=clean_type,
            storage_key=storage_key,
            sha256=validated.sha256,
            media_type=validated.media_type,
            byte_size=validated.byte_size,
            page_count=validated.page_count,
            file_name=validated.file_name,
            scan_status="pending_scan",
            processing_status="queued",
            actor_id=current_user.username,
        )

        job = ProcessingJobRepository.create_job(
            db,
            document_version_id=version.id,
            job_type="document_intake_pipeline",
            max_attempts=3,
        )

        outbox_msg = OutboxRepository.create_message(
            db,
            topic="document_processing",
            payload={"job_id": job.id, "document_version_id": version.id},
        )

        ReviewAuditRepository.create_audit_event(
            db,
            action="DOCUMENT_UPLOAD_ACCEPTED",
            target_type="DocumentVersion",
            target_id=str(version.id),
            actor_id=current_user.username,
            institution_id=app.institution_id,
            details=f'{{"job_id": "{job.id}", "storage_key": "{storage_key}"}}',
        )

        db.commit()
    except Exception as exc:
        db.rollback()
        # Compensation: clean up staged private file on database commit failure
        try:
            storage.delete(storage_key)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist uploaded document records: {exc}",
        ) from exc

    # 4. Reliable dispatch: publish outbox message to queue (or eager execution in tests)
    dispatch_outbox_message(db, outbox_msg)

    # Refresh instances in case eager execution updated states
    db.refresh(doc)
    db.refresh(version)
    db.refresh(job)

    # Support HTTP 202 Accepted if client requested asynchronous response
    if prefer and "respond-async" in prefer.lower():
        response.status_code = status.HTTP_202_ACCEPTED

    polling_url = f"/api/v1/applications/{app.id}/documents/{doc.id}/versions/{version.id}/processing"
    job_read = ProcessingJobRead.model_validate(job)
    job_read.polling_url = polling_url

    doc_read = DocumentRead.model_validate(doc)
    version_read = DocumentVersionRead.model_validate(version)
    doc_read.current_version = version_read

    return DocumentUploadResponse(
        document=doc_read,
        version=version_read,
        job=job_read,
        polling_url=polling_url,
        extracted_fields_count=len(version.extracted_fields),
        notice="Document accepted and queued for background scanning and processing.",
    )


@router.get(
    "/{application_id}/documents/{document_id}/versions/{version_id}/processing",
    response_model=ProcessingJobStatusResponse,
    summary="Get document processing job status",
    description="Poll progress and status of background malware scanning, OCR extraction, and advisory checks.",
)
def get_document_processing_status(
    application_id: int,
    document_id: int,
    version_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJobStatusResponse:
    """Authenticated status-polling endpoint enforcing institutional tenant boundary."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    # Check institutional tenant boundary
    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_READ,
    )

    doc = db.get(Document, document_id)
    if doc is None or doc.application_id != app.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    version = db.get(DocumentVersion, version_id)
    if version is None or version.document_id != doc.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not found",
        )

    job = ProcessingJobRepository.get_latest_for_version(db, version.id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing job not found for this document version",
        )

    findings_count = len(
        list(db.scalars(select(Finding).where(Finding.document_version_id == version.id)).all())
    )

    return ProcessingJobStatusResponse(
        job_id=job.id,
        document_id=doc.id,
        version_id=version.id,
        application_id=app.id,
        state=job.state,
        scan_status=version.scan_status,
        processing_status=version.processing_status,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        last_error_code=job.last_error_code,
        extracted_fields_count=len(version.extracted_fields),
        findings_count=findings_count,
        is_terminal=job.state in ("completed", "failed", "blocked"),
    )


@router.get(
    "/{application_id}/documents",
    response_model=DocumentListResponse,
    summary="List all documents for an application",
)
def list_application_documents(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentListResponse:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_READ,
    )

    docs = DocumentRepository.list_documents_for_application(db, application_id)
    doc_reads: list[DocumentRead] = []
    for doc in docs:
        read_obj = DocumentRead.model_validate(doc)
        if doc.current_version:
            read_obj.current_version = DocumentVersionRead.model_validate(doc.current_version)
        doc_reads.append(read_obj)

    return DocumentListResponse(items=doc_reads, total=len(doc_reads))


@router.get(
    "/{application_id}/documents/{document_id}",
    response_model=DocumentRead,
    summary="Get document slot metadata",
)
def get_application_document(
    application_id: int,
    document_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentRead:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_READ,
    )

    doc = DocumentRepository.get_document(db, document_id)
    if doc is None or doc.application_id != application_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    read_obj = DocumentRead.model_validate(doc)
    if doc.current_version:
        read_obj.current_version = DocumentVersionRead.model_validate(doc.current_version)
    return read_obj


@router.get(
    "/{application_id}/documents/{document_id}/versions",
    response_model=list[DocumentVersionRead],
    summary="List all immutable versions of a document",
)
def list_document_versions(
    application_id: int,
    document_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DocumentVersionRead]:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_READ,
    )

    doc = DocumentRepository.get_document(db, document_id)
    if doc is None or doc.application_id != application_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    versions = DocumentRepository.list_versions(db, document_id)
    return [DocumentVersionRead.model_validate(v) for v in versions]


@router.get(
    "/{application_id}/documents/{document_id}/versions/{version_id}/download",
    summary="Download document binary content",
)
def download_document_version(
    application_id: int,
    document_id: int,
    version_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> Response:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_READ,
    )

    doc = DocumentRepository.get_document(db, document_id)
    if doc is None or doc.application_id != application_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    version = DocumentRepository.get_version(db, version_id)
    if version is None or version.document_id != document_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not found.",
        )

    # Quarantine and security restriction enforcement: download only permitted if clean
    if version.scan_status != "clean" or version.processing_status in ("quarantined", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Document version is quarantined or pending security scan; download is prohibited.",
        )

    data = storage.read(version.storage_key)

    ReviewAuditRepository.create_audit_event(
        db,
        action="DOCUMENT_VERSION_DOWNLOADED",
        target_type="DocumentVersion",
        target_id=str(version.id),
        actor_id=current_user.username,
        institution_id=app.institution_id,
        details=f'{{"version_number": {version.version_number}}}',
    )
    db.commit()

    safe_name = version.file_name or f"document_{doc.id}_v{version.version_number}"
    return Response(
        content=data,
        media_type=version.media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )

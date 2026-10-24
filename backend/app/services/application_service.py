"""Application service layer coordinating business logic and repository transactions."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import Application, Document, DocumentVersion, Institution
from backend.app.repositories.application_repository import ApplicationRepository
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.repositories.institution_repository import InstitutionRepository
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.schemas.application import (
    ApplicationCreate,
    ApplicationUpdate,
    InstitutionCreate,
)
from backend.app.services.exceptions import (
    ApplicationNotFoundError,
    DuplicateDocumentSlotError,
    DuplicateInstitutionError,
    InstitutionNotFoundError,
    InvalidAcademicYearError,
    InvalidApplicationTypeError,
    InvalidStatusTransitionError,
)

SUPPORTED_APPLICATION_TYPES: frozenset[str] = frozenset(
    {"eoa", "new_program", "intake_change"}
)

VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "closed"},
    "submitted": {"processing", "review_required", "closed"},
    "processing": {"review_required", "reviewed", "closed"},
    "review_required": {"reviewed", "closed"},
    "reviewed": {"closed"},
    "closed": set(),
}

ACADEMIC_YEAR_PATTERN = re.compile(r"^(20\d{2})-(20\d{2})$")


def validate_academic_year(academic_year: str) -> str:
    """Validate that academic year matches YYYY-YYYY with consecutive years."""
    match = ACADEMIC_YEAR_PATTERN.match(academic_year.strip())
    if not match:
        raise InvalidAcademicYearError(
            f"Invalid academic year {academic_year!r}. Format must be YYYY-YYYY (e.g. '2026-2027')."
        )
    start_year, end_year = int(match.group(1)), int(match.group(2))
    if end_year != start_year + 1:
        raise InvalidAcademicYearError(
            f"Academic year span {academic_year!r} must be consecutive years (e.g. '2026-2027')."
        )
    return f"{start_year}-{end_year}"


class ApplicationService:
    """Coordinates institution and application business logic and transactions."""

    def __init__(
        self,
        institution_repo: type[InstitutionRepository] = InstitutionRepository,
        application_repo: type[ApplicationRepository] = ApplicationRepository,
        document_repo: type[DocumentRepository] = DocumentRepository,
        review_audit_repo: type[ReviewAuditRepository] = ReviewAuditRepository,
    ) -> None:
        self.institution_repo = institution_repo
        self.application_repo = application_repo
        self.document_repo = document_repo
        self.review_audit_repo = review_audit_repo

    def create_institution(
        self,
        db: Session,
        data: InstitutionCreate,
    ) -> Institution:
        """Create an institution if unique; raise DuplicateInstitutionError otherwise."""
        existing = self.institution_repo.get_by_identifier(db, data.institution_id)
        if existing:
            raise DuplicateInstitutionError(
                f"Institution with identifier '{data.institution_id}' already exists."
            )

        try:
            institution = self.institution_repo.create(
                db,
                institution_id=data.institution_id,
                display_name=data.display_name,
                status=data.status,
            )
            db.commit()
            db.refresh(institution)
            return institution
        except IntegrityError as exc:
            db.rollback()
            raise DuplicateInstitutionError(
                f"Institution with identifier '{data.institution_id}' already exists."
            ) from exc
        except Exception:
            db.rollback()
            raise

    def get_institution(
        self,
        db: Session,
        institution_id: int,
    ) -> Institution:
        """Retrieve an institution by ID or raise InstitutionNotFoundError."""
        institution = self.institution_repo.get_by_id(db, institution_id)
        if not institution:
            raise InstitutionNotFoundError(
                f"Institution with ID {institution_id} not found."
            )
        return institution

    def get_institution_by_identifier(
        self,
        db: Session,
        identifier: str,
    ) -> Institution:
        """Retrieve an institution by string identifier or raise InstitutionNotFoundError."""
        institution = self.institution_repo.get_by_identifier(db, identifier)
        if not institution:
            raise InstitutionNotFoundError(
                f"Institution with identifier {identifier!r} not found."
            )
        return institution

    def create_application(
        self,
        db: Session,
        data: ApplicationCreate,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> Application:
        """Validate prerequisites and create an application within a transaction."""
        institution = self.institution_repo.get_by_id(db, data.institution_id)
        if not institution:
            raise InstitutionNotFoundError(
                f"Cannot create application: Institution ID {data.institution_id} does not exist."
            )

        if data.application_type not in SUPPORTED_APPLICATION_TYPES:
            raise InvalidApplicationTypeError(
                f"Unsupported application type '{data.application_type}'. "
                f"Must be one of {sorted(SUPPORTED_APPLICATION_TYPES)}."
            )

        validated_year = validate_academic_year(data.academic_year)

        try:
            application = self.application_repo.create(
                db,
                institution_id=data.institution_id,
                application_type=data.application_type,
                academic_year=validated_year,
                status=data.status or "draft",
            )
            db.flush()

            self.review_audit_repo.create_audit_event(
                db,
                action="APPLICATION_CREATED",
                target_type="Application",
                target_id=str(application.id),
                actor_id=actor_id,
                institution_id=data.institution_id,
                request_id=request_id,
                details=f'{{"application_type": "{data.application_type}", "academic_year": "{validated_year}"}}',
            )

            db.commit()
            db.refresh(application)
            return application
        except Exception:
            db.rollback()
            raise

    def get_application(
        self,
        db: Session,
        application_id: int,
    ) -> Application:
        """Retrieve an application by ID or raise ApplicationNotFoundError."""
        app = self.application_repo.get_by_id(db, application_id)
        if not app:
            raise ApplicationNotFoundError(
                f"Application with ID {application_id} not found."
            )
        return app

    def list_applications_for_institution(
        self,
        db: Session,
        institution_id: int,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
    ) -> tuple[list[Application], int]:
        """List applications for an existing institution with pagination and optional status filter."""
        self.get_institution(db, institution_id)
        return self.application_repo.list_by_institution(
            db, institution_id, skip=skip, limit=limit, status=status
        )

    def update_application(
        self,
        db: Session,
        application_id: int,
        data: ApplicationUpdate,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> Application:
        """Update permitted fields on an existing application with transaction management."""
        app = self.get_application(db, application_id)
        updates: dict[str, Any] = {}

        if data.academic_year is not None:
            updates["academic_year"] = validate_academic_year(data.academic_year)

        if data.status is not None:
            if data.status not in VALID_STATUS_TRANSITIONS.get(app.status, set()):
                raise InvalidStatusTransitionError(
                    f"Illegal lifecycle transition from '{app.status}' to '{data.status}'. "
                    f"Permitted transitions: {sorted(VALID_STATUS_TRANSITIONS.get(app.status, set()))}"
                )
            updates["status"] = data.status

        updates["updated_at"] = datetime.now(timezone.utc)

        try:
            self.application_repo.update(db, app, **updates)
            self.review_audit_repo.create_audit_event(
                db,
                action="APPLICATION_UPDATED",
                target_type="Application",
                target_id=str(app.id),
                actor_id=actor_id,
                institution_id=app.institution_id,
                request_id=request_id,
                details=str(updates),
            )
            db.commit()
            db.refresh(app)
            return app
        except Exception:
            db.rollback()
            raise

    def transition_status(
        self,
        db: Session,
        application_id: int,
        new_status: str,
        *,
        reviewer_id: str | None = None,
        comment: str | None = None,
        request_id: str | None = None,
    ) -> Application:
        """Transition application lifecycle status and record optional ReviewAction atomically."""
        app = self.get_application(db, application_id)

        valid_targets = VALID_STATUS_TRANSITIONS.get(app.status, set())
        if new_status not in valid_targets:
            raise InvalidStatusTransitionError(
                f"Cannot transition application {application_id} from '{app.status}' to '{new_status}'. "
                f"Allowed transitions: {sorted(valid_targets)}"
            )

        try:
            self.application_repo.update(
                db,
                app,
                status=new_status,
                updated_at=datetime.now(timezone.utc),
            )

            if reviewer_id is not None:
                self.review_audit_repo.create_review_action(
                    db,
                    application_id=app.id,
                    reviewer_id=reviewer_id,
                    action=new_status,
                    comment=comment,
                )

            self.review_audit_repo.create_audit_event(
                db,
                action=f"STATUS_TRANSITION_{new_status.upper()}",
                target_type="Application",
                target_id=str(app.id),
                actor_id=reviewer_id,
                institution_id=app.institution_id,
                request_id=request_id,
                details=f'{{"from": "{app.status}", "to": "{new_status}"}}',
            )

            db.commit()
            db.refresh(app)
            return app
        except Exception:
            db.rollback()
            raise

    def add_document_version(
        self,
        db: Session,
        application_id: int,
        document_type: str,
        *,
        storage_key: str,
        sha256: str,
        media_type: str,
        byte_size: int,
        page_count: int | None = None,
        file_name: str | None = None,
        scan_status: str | None = "pending_scan",
        processing_status: str = "queued",
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> tuple[Document, DocumentVersion]:
        """Add an immutable document version to an application slot within a transaction."""
        app = self.get_application(db, application_id)

        try:
            doc = self.document_repo.get_document_by_type(db, app.id, document_type)
            if not doc:
                doc = self.document_repo.create_document(
                    db, application_id=app.id, document_type=document_type
                )
                db.flush()

            existing_versions = self.document_repo.list_versions(db, doc.id)
            next_version = len(existing_versions) + 1

            version = self.document_repo.add_version(
                db,
                document_id=doc.id,
                version_number=next_version,
                storage_key=storage_key,
                sha256=sha256,
                media_type=media_type,
                byte_size=byte_size,
                page_count=page_count,
                file_name=file_name,
                scan_status=scan_status,
                processing_status=processing_status,
            )
            db.flush()

            self.document_repo.set_current_version(db, doc, version)

            self.review_audit_repo.create_audit_event(
                db,
                action="DOCUMENT_VERSION_ADDED",
                target_type="DocumentVersion",
                target_id=str(version.id),
                actor_id=actor_id,
                institution_id=app.institution_id,
                request_id=request_id,
                details=f'{{"document_type": "{document_type}", "version": {next_version}}}',
            )

            db.commit()
            db.refresh(doc)
            db.refresh(version)
            return doc, version
        except IntegrityError as exc:
            db.rollback()
            raise DuplicateDocumentSlotError(
                f"Document version conflict for '{document_type}': {exc}"
            ) from exc
        except Exception:
            db.rollback()
            raise

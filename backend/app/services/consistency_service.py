"""Business logic and institution authorization for consistency records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import verify_institution_membership
from backend.app.core.rbac import (
    PERMISSION_APPLICATION_READ,
    PERMISSION_APPLICATION_UPDATE,
    has_permission,
)
from backend.app.db.models import (
    Application,
    ConsistencyCheck,
    ConsistencyFinding,
    User,
)
from backend.app.repositories.application_repository import ApplicationRepository
from backend.app.repositories.consistency_check_repository import (
    ConsistencyCheckRepository,
)
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.schemas.consistency import (
    ConsistencyCheckCreate,
    ConsistencyFindingCreate,
    ConsistencyFindingUpdate,
)

T = TypeVar("T")


def _not_found(detail: str = "Resource not found or access denied.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ConsistencyCheckService:
    """Authorize each operation before reading or changing tenant-owned records."""

    @staticmethod
    def _authorized_application(
        db: Session,
        *,
        application_id: int,
        user: User,
        permission: str,
    ) -> Application:
        application = ApplicationRepository.get_by_id(db, application_id)
        if application is None:
            raise _not_found("Application not found.")
        verify_institution_membership(
            db, user, application.institution_id, required_permission=permission
        )
        return application

    @classmethod
    def _authorized_check(
        cls,
        db: Session,
        *,
        check_id: int,
        user: User,
        permission: str,
    ) -> ConsistencyCheck:
        check = ConsistencyCheckRepository.get_check(db, check_id)
        if check is None:
            raise _not_found("Consistency check not found.")
        cls._authorized_application(
            db,
            application_id=check.application_id,
            user=user,
            permission=permission,
        )
        return check

    @classmethod
    def _authorized_finding(
        cls,
        db: Session,
        *,
        finding_id: int,
        user: User,
        permission: str,
    ) -> tuple[ConsistencyFinding, ConsistencyCheck]:
        finding = ConsistencyCheckRepository.get_finding(db, finding_id)
        if finding is None:
            raise _not_found("Consistency finding not found.")
        check = cls._authorized_check(
            db,
            check_id=finding.consistency_check_id,
            user=user,
            permission=permission,
        )
        return finding, check

    @staticmethod
    def _commit(db: Session, record: T) -> T:
        try:
            db.commit()
            db.refresh(record)
            return record
        except IntegrityError as exc:
            db.rollback()
            raise _not_found("Parent application or consistency check not found.") from exc
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _flush(db: Session) -> None:
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise _not_found("Parent application or consistency check not found.") from exc
        except Exception:
            db.rollback()
            raise

    @classmethod
    def create_check(
        cls, db: Session, *, payload: ConsistencyCheckCreate, user: User
    ) -> ConsistencyCheck:
        application = cls._authorized_application(
            db,
            application_id=payload.application_id,
            user=user,
            permission=PERMISSION_APPLICATION_UPDATE,
        )
        check = ConsistencyCheckRepository.create_check(
            db,
            application_id=application.id,
            check_name=payload.check_name,
            description=payload.description,
            related_field=payload.related_field,
        )
        cls._flush(db)
        ReviewAuditRepository.create_audit_event(
            db,
            action="CONSISTENCY_CHECK_CREATED",
            target_type="ConsistencyCheck",
            target_id=str(check.id),
            actor_id=user.username,
            institution_id=application.institution_id,
            details=json.dumps({"application_id": application.id, "check_name": check.check_name}),
        )
        return cls._commit(db, check)

    @classmethod
    def get_check(cls, db: Session, *, check_id: int, user: User) -> ConsistencyCheck:
        return cls._authorized_check(
            db,
            check_id=check_id,
            user=user,
            permission=PERMISSION_APPLICATION_READ,
        )

    @classmethod
    def list_checks(
        cls,
        db: Session,
        *,
        user: User,
        application_id: int | None = None,
        status_filter: str | None = None,
    ) -> list[ConsistencyCheck]:
        if application_id is not None:
            application = cls._authorized_application(
                db,
                application_id=application_id,
                user=user,
                permission=PERMISSION_APPLICATION_READ,
            )
            institution_ids = [application.institution_id]
        else:
            institution_ids = sorted(
                {
                    membership.institution_id
                    for membership in UserRepository.get_active_memberships(db, user.id)
                    if has_permission(membership.role, PERMISSION_APPLICATION_READ)
                }
            )
        return ConsistencyCheckRepository.list_checks(
            db,
            institution_ids=institution_ids,
            application_id=application_id,
            status_filter=status_filter,
        )

    @classmethod
    def create_finding(
        cls, db: Session, *, payload: ConsistencyFindingCreate, user: User
    ) -> ConsistencyFinding:
        check = cls._authorized_check(
            db,
            check_id=payload.consistency_check_id,
            user=user,
            permission=PERMISSION_APPLICATION_UPDATE,
        )
        finding = ConsistencyCheckRepository.create_finding(
            db,
            consistency_check_id=check.id,
            field_name=payload.field_name,
            value_1=payload.value_1,
            value_2=payload.value_2,
            severity=payload.severity,
            confidence=payload.confidence,
            description=payload.description,
            evidence=payload.evidence,
        )
        check.status = "discrepancy_detected"
        check.updated_at = datetime.now(UTC)
        cls._flush(db)
        ReviewAuditRepository.create_audit_event(
            db,
            action="CONSISTENCY_FINDING_CREATED",
            target_type="ConsistencyFinding",
            target_id=str(finding.id),
            actor_id=user.username,
            institution_id=check.application.institution_id,
            details=json.dumps({"consistency_check_id": check.id, "field_name": finding.field_name}),
        )
        return cls._commit(db, finding)

    @classmethod
    def get_finding(
        cls, db: Session, *, finding_id: int, user: User
    ) -> ConsistencyFinding:
        finding, _ = cls._authorized_finding(
            db,
            finding_id=finding_id,
            user=user,
            permission=PERMISSION_APPLICATION_READ,
        )
        return finding

    @classmethod
    def list_findings(
        cls,
        db: Session,
        *,
        check_id: int,
        user: User,
        severity_filter: str | None = None,
        resolved: bool | None = None,
    ) -> list[ConsistencyFinding]:
        cls._authorized_check(
            db,
            check_id=check_id,
            user=user,
            permission=PERMISSION_APPLICATION_READ,
        )
        return ConsistencyCheckRepository.list_findings(
            db,
            consistency_check_id=check_id,
            severity_filter=severity_filter,
            resolved=resolved,
        )

    @classmethod
    def update_finding(
        cls,
        db: Session,
        *,
        finding_id: int,
        payload: ConsistencyFindingUpdate,
        user: User,
    ) -> ConsistencyFinding:
        finding, check = cls._authorized_finding(
            db,
            finding_id=finding_id,
            user=user,
            permission=PERMISSION_APPLICATION_UPDATE,
        )
        updates = payload.model_dump(exclude_unset=True)
        for field in ("description",):
            if field in updates and updates[field] is not None:
                updates[field] = updates[field].strip()
        ConsistencyCheckRepository.update_finding(finding, updates=updates)

        if "resolved" in updates:
            cls._flush(db)
            unresolved = ConsistencyCheckRepository.list_findings(
                db,
                consistency_check_id=check.id,
                resolved=False,
            )
            check.status = "discrepancy_detected" if unresolved else "resolved"
            check.updated_at = datetime.now(UTC)

        ReviewAuditRepository.create_audit_event(
            db,
            action="CONSISTENCY_FINDING_UPDATED",
            target_type="ConsistencyFinding",
            target_id=str(finding.id),
            actor_id=user.username,
            institution_id=check.application.institution_id,
            details=json.dumps({"consistency_check_id": check.id, "updated_fields": sorted(updates)}),
        )
        return cls._commit(db, finding)

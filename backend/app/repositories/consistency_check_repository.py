"""Persistence operations for consistency checks and their findings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Application, ConsistencyCheck, ConsistencyFinding


class ConsistencyCheckRepository:
    """Encapsulate consistency data access; tenant authorization belongs to the service."""

    @staticmethod
    def get_check(db: Session, check_id: int) -> ConsistencyCheck | None:
        return db.get(ConsistencyCheck, check_id)

    @staticmethod
    def list_checks(
        db: Session,
        *,
        institution_ids: list[int],
        application_id: int | None = None,
        status_filter: str | None = None,
    ) -> list[ConsistencyCheck]:
        if not institution_ids:
            return []

        stmt = (
            select(ConsistencyCheck)
            .join(Application, ConsistencyCheck.application_id == Application.id)
            .where(Application.institution_id.in_(institution_ids))
        )
        if application_id is not None:
            stmt = stmt.where(ConsistencyCheck.application_id == application_id)
        if status_filter is not None:
            stmt = stmt.where(ConsistencyCheck.status == status_filter)
        stmt = stmt.order_by(ConsistencyCheck.created_at.desc(), ConsistencyCheck.id.desc())
        return list(db.scalars(stmt).all())

    @staticmethod
    def create_check(
        db: Session,
        *,
        application_id: int,
        check_name: str,
        description: str | None,
        related_field: str | None,
    ) -> ConsistencyCheck:
        check = ConsistencyCheck(
            application_id=application_id,
            check_name=check_name.strip(),
            description=description.strip() if description else None,
            related_field=related_field.strip() if related_field else None,
            status="pending",
        )
        db.add(check)
        return check

    @staticmethod
    def get_finding(db: Session, finding_id: int) -> ConsistencyFinding | None:
        return db.get(ConsistencyFinding, finding_id)

    @staticmethod
    def list_findings(
        db: Session,
        *,
        consistency_check_id: int,
        severity_filter: str | None = None,
        resolved: bool | None = None,
    ) -> list[ConsistencyFinding]:
        stmt = select(ConsistencyFinding).where(
            ConsistencyFinding.consistency_check_id == consistency_check_id
        )
        if severity_filter is not None:
            stmt = stmt.where(ConsistencyFinding.severity == severity_filter)
        if resolved is not None:
            stmt = stmt.where(ConsistencyFinding.resolved.is_(resolved))
        stmt = stmt.order_by(ConsistencyFinding.created_at.desc(), ConsistencyFinding.id.desc())
        return list(db.scalars(stmt).all())

    @staticmethod
    def create_finding(
        db: Session,
        *,
        consistency_check_id: int,
        field_name: str,
        value_1: str,
        value_2: str,
        severity: str,
        confidence: float | None,
        description: str,
        evidence: dict[str, object] | None,
    ) -> ConsistencyFinding:
        finding = ConsistencyFinding(
            consistency_check_id=consistency_check_id,
            field_name=field_name.strip(),
            value_1=value_1,
            value_2=value_2,
            severity=severity,
            confidence=confidence,
            description=description.strip(),
            evidence=evidence,
            resolved=False,
        )
        db.add(finding)
        return finding

    @staticmethod
    def update_finding(
        finding: ConsistencyFinding,
        *,
        updates: dict[str, object],
    ) -> ConsistencyFinding:
        for field, value in updates.items():
            setattr(finding, field, value)
        return finding

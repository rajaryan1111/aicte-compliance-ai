"""Application repository for database access."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models import Application


class ApplicationRepository:
    """Encapsulates persistence operations for Application entities."""

    @staticmethod
    def get_by_id(db: Session, application_id: int) -> Application | None:
        """Find an application by its primary key ID."""
        return db.get(Application, application_id)

    @staticmethod
    def create(
        db: Session,
        *,
        institution_id: int,
        application_type: str,
        academic_year: str,
        status: str = "draft",
    ) -> Application:
        """Add a new Application instance to the session."""
        application = Application(
            institution_id=institution_id,
            application_type=application_type,
            academic_year=academic_year,
            status=status,
        )
        db.add(application)
        return application

    @staticmethod
    def list_by_institution(
        db: Session,
        institution_id: int,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
    ) -> tuple[list[Application], int]:
        """List applications for an institution with pagination and return total count."""
        count_stmt = (
            select(func.count())
            .select_from(Application)
            .where(Application.institution_id == institution_id)
        )
        if status is not None:
            count_stmt = count_stmt.where(Application.status == status)
        total = db.scalar(count_stmt) or 0

        stmt = (
            select(Application)
            .where(Application.institution_id == institution_id)
        )
        if status is not None:
            stmt = stmt.where(Application.status == status)

        stmt = (
            stmt.order_by(Application.created_at.desc(), Application.id.desc())
            .offset(skip)
            .limit(limit)
        )
        records = list(db.scalars(stmt).all())
        return records, total

    @staticmethod
    def update(
        db: Session,
        application: Application,
        **fields: Any,
    ) -> Application:
        """Update permitted fields on an Application instance."""
        for field, value in fields.items():
            if hasattr(application, field) and value is not None:
                setattr(application, field, value)
        return application

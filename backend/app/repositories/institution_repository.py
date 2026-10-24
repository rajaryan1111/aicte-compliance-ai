"""Institution repository for database access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Institution


class InstitutionRepository:
    """Encapsulates persistence operations for the Institution entity."""

    @staticmethod
    def get_by_id(db: Session, institution_id: int) -> Institution | None:
        """Find an institution by its primary key ID."""
        return db.get(Institution, institution_id)

    @staticmethod
    def get_by_identifier(db: Session, institution_id: str) -> Institution | None:
        """Find an institution by its unique institutional string identifier."""
        stmt = select(Institution).where(Institution.institution_id == institution_id)
        return db.scalar(stmt)

    @staticmethod
    def create(
        db: Session,
        *,
        institution_id: str,
        display_name: str,
        status: str = "active",
    ) -> Institution:
        """Add a new Institution instance to the session."""
        institution = Institution(
            institution_id=institution_id,
            display_name=display_name,
            status=status,
        )
        db.add(institution)
        return institution

    @staticmethod
    def list(
        db: Session,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Institution]:
        """List institutions with pagination."""
        stmt = (
            select(Institution)
            .order_by(Institution.id.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

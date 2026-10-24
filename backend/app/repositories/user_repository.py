"""User and membership repository for authentication and tenant authorization."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import InstitutionMembership, User


class UserRepository:
    """Encapsulates persistence operations for User and InstitutionMembership entities."""

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> User | None:
        """Find a user by primary key."""
        return db.get(User, user_id)

    @staticmethod
    def get_by_username(db: Session, username: str) -> User | None:
        """Find a user by unique username (case-sensitive exact match)."""
        stmt = select(User).where(User.username == username)
        return db.scalar(stmt)

    @staticmethod
    def create(
        db: Session,
        *,
        username: str,
        hashed_password: str,
        display_name: str | None = None,
        is_active: bool = True,
    ) -> User:
        """Create a new user account."""
        user = User(
            username=username,
            hashed_password=hashed_password,
            display_name=display_name,
            is_active=is_active,
        )
        db.add(user)
        return user

    @staticmethod
    def create_membership(
        db: Session,
        *,
        user_id: int,
        institution_id: int,
        role: str,
        is_active: bool = True,
    ) -> InstitutionMembership:
        """Assign a user to an institution with a role."""
        membership = InstitutionMembership(
            user_id=user_id,
            institution_id=institution_id,
            role=role,
            is_active=is_active,
        )
        db.add(membership)
        return membership

    @staticmethod
    def get_membership(
        db: Session,
        user_id: int,
        institution_id: int,
    ) -> InstitutionMembership | None:
        """Retrieve membership for a specific user and institution."""
        stmt = select(InstitutionMembership).where(
            InstitutionMembership.user_id == user_id,
            InstitutionMembership.institution_id == institution_id,
        )
        return db.scalar(stmt)

    @staticmethod
    def get_active_memberships(
        db: Session,
        user_id: int,
    ) -> list[InstitutionMembership]:
        """List all active institution memberships for a user."""
        stmt = (
            select(InstitutionMembership)
            .where(
                InstitutionMembership.user_id == user_id,
                InstitutionMembership.is_active.is_(True),
            )
            .order_by(InstitutionMembership.institution_id.asc())
        )
        return list(db.scalars(stmt).all())

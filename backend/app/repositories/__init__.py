"""Repository package for AICTE Compliance AI."""

from backend.app.repositories.application_repository import ApplicationRepository
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.repositories.institution_repository import InstitutionRepository
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.repositories.validation_repository import ValidationRepository

__all__ = [
    "ApplicationRepository",
    "DocumentRepository",
    "InstitutionRepository",
    "ReviewAuditRepository",
    "UserRepository",
    "ValidationRepository",
]


"""Services package for AICTE Compliance AI."""

from backend.app.services.application_service import ApplicationService
from backend.app.services.exceptions import (
    ApplicationNotFoundError,
    ConflictError,
    DuplicateDocumentSlotError,
    DuplicateInstitutionError,
    DuplicateRecordError,
    InstitutionNotFoundError,
    InvalidAcademicYearError,
    InvalidApplicationTypeError,
    InvalidStatusTransitionError,
    NotFoundError,
    ServiceError,
    ValidationError,
)

__all__ = [
    "ApplicationNotFoundError",
    "ApplicationService",
    "ConflictError",
    "DuplicateDocumentSlotError",
    "DuplicateInstitutionError",
    "DuplicateRecordError",
    "InstitutionNotFoundError",
    "InvalidAcademicYearError",
    "InvalidApplicationTypeError",
    "InvalidStatusTransitionError",
    "NotFoundError",
    "ServiceError",
    "ValidationError",
]

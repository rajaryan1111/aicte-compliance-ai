"""Domain and service exceptions for AICTE Compliance AI."""

from __future__ import annotations


class ServiceError(Exception):
    """Base exception for all service layer errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    """Base exception when a requested entity does not exist."""
    pass


class InstitutionNotFoundError(NotFoundError):
    """Raised when an institution cannot be found."""
    pass


class ApplicationNotFoundError(NotFoundError):
    """Raised when an application cannot be found."""
    pass


class DocumentNotFoundError(NotFoundError):
    """Raised when a document cannot be found."""
    pass


class ValidationRunNotFoundError(NotFoundError):
    """Raised when a validation run cannot be found."""
    pass


class ValidationError(ServiceError):
    """Base exception for domain validation errors."""
    pass


class InvalidApplicationTypeError(ValidationError):
    """Raised when an unsupported application type is provided."""
    pass


class InvalidAcademicYearError(ValidationError):
    """Raised when an academic year string is malformed or invalid."""
    pass


class InvalidStatusTransitionError(ValidationError):
    """Raised when an illegal application lifecycle transition is attempted."""
    pass


class ConflictError(ServiceError):
    """Base exception for constraint and unique conflicts."""
    pass


class DuplicateInstitutionError(ConflictError):
    """Raised when an institution with the same identifier already exists."""
    pass


class DuplicateDocumentSlotError(ConflictError):
    """Raised when a duplicate document type slot is created for an application."""
    pass


class DuplicateRecordError(ConflictError):
    """Raised when a general unique constraint violation occurs."""
    pass


class RemediationPlanNotFoundError(NotFoundError):
    """Raised when a remediation plan is absent from the resolved tenant scope."""

    pass


class RemediationTaskNotFoundError(NotFoundError):
    """Raised when a task key does not exist inside the addressed plan."""

    pass


class StaleRemediationTaskVersionError(ConflictError):
    """Raised when a client updates a task using a version that is no longer current."""

    def __init__(self, expected: int, received: int) -> None:
        super().__init__(
            f"Task was modified by another user. Current version is {expected}, "
            f"the request carried {received}. Reload the plan and retry."
        )
        self.expected = expected
        self.received = received

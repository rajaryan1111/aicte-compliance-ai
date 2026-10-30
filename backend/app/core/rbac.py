"""Server-side Role-Based Access Control (RBAC) definitions and permission checks."""

from __future__ import annotations

ROLE_INSTITUTION_ADMIN = "institution_admin"
ROLE_SCRUTINY_OFFICER = "scrutiny_officer"
ROLE_AUDITOR = "auditor"
ROLE_REGULATORY_DIRECTOR = "regulatory_director"
ROLE_SUPER_ADMIN = "super_admin"

PERMISSION_APPLICATION_CREATE = "application:create"
PERMISSION_APPLICATION_READ = "application:read"
PERMISSION_APPLICATION_UPDATE = "application:update"
PERMISSION_REVIEW_READ = "review:read"
PERMISSION_REVIEW_ACTION = "review:action"
PERMISSION_FINDING_WAIVE = "finding:waive"
PERMISSION_AUDIT_PACKAGE_CREATE = "audit_package:create"
PERMISSION_AUDIT_PACKAGE_READ = "audit_package:read"
PERMISSION_RULE_READ = "rule:read"
PERMISSION_RULE_VERIFY = "rule:verify"
PERMISSION_RULE_APPROVE = "rule:approve"
PERMISSION_RETENTION_MANAGE = "retention:manage"

# Centralized role-to-permission mapping
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_INSTITUTION_ADMIN: frozenset({
        PERMISSION_APPLICATION_CREATE,
        PERMISSION_APPLICATION_READ,
        PERMISSION_APPLICATION_UPDATE,
        PERMISSION_REVIEW_READ,
        PERMISSION_AUDIT_PACKAGE_CREATE,
        PERMISSION_AUDIT_PACKAGE_READ,
        PERMISSION_RULE_READ,
    }),
    ROLE_SCRUTINY_OFFICER: frozenset({
        PERMISSION_APPLICATION_READ,
        PERMISSION_APPLICATION_UPDATE,
        PERMISSION_REVIEW_READ,
        PERMISSION_REVIEW_ACTION,
        PERMISSION_AUDIT_PACKAGE_CREATE,
        PERMISSION_AUDIT_PACKAGE_READ,
        PERMISSION_RULE_READ,
        PERMISSION_RETENTION_MANAGE,
    }),
    ROLE_REGULATORY_DIRECTOR: frozenset({
        PERMISSION_APPLICATION_READ,
        PERMISSION_REVIEW_READ,
        PERMISSION_REVIEW_ACTION,
        PERMISSION_AUDIT_PACKAGE_READ,
        PERMISSION_RULE_READ,
        PERMISSION_RULE_VERIFY,
        PERMISSION_RULE_APPROVE,
        PERMISSION_RETENTION_MANAGE,
    }),
    ROLE_AUDITOR: frozenset({
        PERMISSION_APPLICATION_READ,
        PERMISSION_REVIEW_READ,
        PERMISSION_AUDIT_PACKAGE_READ,
        PERMISSION_RULE_READ,
    }),
    ROLE_SUPER_ADMIN: frozenset({
        PERMISSION_APPLICATION_CREATE,
        PERMISSION_APPLICATION_READ,
        PERMISSION_APPLICATION_UPDATE,
        PERMISSION_REVIEW_READ,
        PERMISSION_REVIEW_ACTION,
        PERMISSION_FINDING_WAIVE,
        PERMISSION_AUDIT_PACKAGE_CREATE,
        PERMISSION_AUDIT_PACKAGE_READ,
        PERMISSION_RULE_READ,
        PERMISSION_RULE_VERIFY,
        PERMISSION_RULE_APPROVE,
        PERMISSION_RETENTION_MANAGE,
    }),
}


def has_permission(role: str | None, permission: str) -> bool:
    """Check if a given role possesses the requested permission.

    Denies by default if role is None or unrecognized.
    """
    if not role:
        return False
    allowed = ROLE_PERMISSIONS.get(role, frozenset())
    return permission in allowed

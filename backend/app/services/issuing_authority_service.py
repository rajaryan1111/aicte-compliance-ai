"""Service orchestrating issuing-authority verification attempts and audit logging."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Application, AuditEvent, DocumentVersion, VerificationAttempt
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.services.verification_adapter import (
    SimulatedDemoIssuerAdapter,
    VerificationRequestPayload,
    VerificationResultPayload,
    get_adapter,
    list_available_adapters,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IssuingAuthorityService:
    """Orchestrates official and simulated issuing-authority verification workflows."""

    @classmethod
    def request_verification(
        cls,
        db: Session,
        *,
        application_id: int,
        document_version_id: int,
        adapter_name: str | None = None,
        actor_id: str = "system",
        force_simulated: bool = False,
    ) -> VerificationAttempt:
        """Execute a verification attempt against an external adapter and record the result."""
        version = db.get(DocumentVersion, document_version_id)
        if version is None:
            raise ValueError(f"DocumentVersion {document_version_id} not found.")

        app = db.get(Application, application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found.")

        doc_type = version.document.document_type if version.document else "unknown"

        # Determine target adapter
        if force_simulated:
            adapter = SimulatedDemoIssuerAdapter()
        else:
            selected_name = adapter_name or "digilocker_national_gateway"
            adapter = get_adapter(selected_name)
            if adapter is None:
                adapter = SimulatedDemoIssuerAdapter()

        # Extract available fields for querying
        extracted_map = {f.field_name: f for f in version.extracted_fields}
        cert_num = None
        for key in ("certificate_number", "noc_number", "application_reference"):
            if key in extracted_map and extracted_map[key].normalized_value:
                cert_num = extracted_map[key].normalized_value
                break

        authority_str = None
        for key in ("issuing_authority", "authority"):
            if key in extracted_map and extracted_map[key].normalized_value:
                authority_str = extracted_map[key].normalized_value
                break

        issue_date_str = (
            extracted_map["issue_date"].normalized_value
            if "issue_date" in extracted_map
            else None
        )
        expiry_date_str = (
            extracted_map["valid_until"].normalized_value
            if "valid_until" in extracted_map
            else (extracted_map["expiry_date"].normalized_value if "expiry_date" in extracted_map else None)
        )

        inst_id = app.institution.institution_id if app.institution else str(app.institution_id)

        req_payload = VerificationRequestPayload(
            application_id=app.id,
            document_version_id=version.id,
            document_category=doc_type,
            certificate_number=cert_num,
            claimed_issuing_authority=authority_str,
            issue_date=issue_date_str,
            expiry_date=expiry_date_str,
            institution_id=inst_id,
            actor_id=actor_id,
            simulated=force_simulated or not adapter.is_official_source,
        )

        # Execute adapter
        result: VerificationResultPayload = adapter.verify(req_payload)

        # Generate attempt reference
        now = _utc_now()
        attempt_ref = f"VA-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # Persist attempt record
        attempt = VerificationAttempt(
            application_id=app.id,
            document_version_id=version.id,
            attempt_reference=attempt_ref,
            adapter_name=result.adapter_name,
            source_title=result.source_title,
            is_official_source=result.is_official_source,
            status=result.status,
            submitted_attributes=json.dumps(result.submitted_attributes),
            returned_attributes=json.dumps(result.returned_attributes),
            failure_reason=result.failure_reason,
            source_reference=result.source_reference,
            actor_id=actor_id,
            created_at=result.verified_at,
        )
        db.add(attempt)
        db.flush()

        # Audit event
        ReviewAuditRepository.create_audit_event(
            db,
            action="ISSUING_AUTHORITY_VERIFICATION",
            target_type="VerificationAttempt",
            target_id=attempt_ref,
            actor_id=actor_id,
            institution_id=app.institution_id,
            details=json.dumps({
                "adapter": result.adapter_name,
                "status": result.status,
                "document_version_id": version.id,
                "source_reference": result.source_reference,
            }),
        )
        db.commit()
        db.refresh(attempt)
        return attempt

    @classmethod
    def list_attempts(cls, db: Session, application_id: int) -> list[VerificationAttempt]:
        """List all recorded verification attempts for an application in reverse chronological order."""
        stmt = (
            select(VerificationAttempt)
            .where(VerificationAttempt.application_id == application_id)
            .order_by(VerificationAttempt.created_at.desc())
        )
        return list(db.scalars(stmt).all())

    @classmethod
    def get_available_adapters(cls) -> list[dict[str, Any]]:
        """Return available adapter registry metadata."""
        return list_available_adapters()

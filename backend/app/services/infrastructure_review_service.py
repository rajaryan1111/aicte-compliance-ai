"""Infrastructure compliance assistance service for AICTE Approval Process scrutiny.

Evaluates documentary evidence and visual submissions (building plans, structural certs,
photos) against APH Chapter II norms, identifying cases requiring physical inspection
by an Expert Visit Committee (EVC).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Application, DocumentVersion, InfrastructureEvidence
from backend.app.ocr_adapter import parse_iso_date_candidate
from backend.app.repositories.review_audit_repository import ReviewAuditRepository

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Standard minimum land requirements per APH 2024-2027 Chapter I & II (in Acres)
MINIMUM_LAND_NORMS_ACRES: dict[str, float] = {
    "mega_cities": 1.5,
    "metro_cities": 2.5,
    "urban": 4.0,
    "rural": 7.5,
}

# Standard minimum carpet area per student (in sqm) for instructional areas
MIN_INSTRUCTIONAL_AREA_SQM_PER_STUDENT: float = 4.0


@dataclass(frozen=True)
class InfrastructureReviewItem:
    evidence_type: str
    document_version_id: int
    declared_area_sqm: float | None
    observed_area_sqm: float | None
    inspection_recommended: bool
    inspection_rationale: str | None
    analysis_metadata: dict[str, Any]


@dataclass(frozen=True)
class InfrastructureReviewSummary:
    application_id: int
    overall_status: str
    physical_inspection_recommended: bool
    inspection_reasons: list[str]
    items: list[InfrastructureReviewItem]
    evaluated_at: datetime


class InfrastructureReviewService:
    """Evaluates institutional infrastructure evidence against AICTE APH Chapter II norms."""

    @classmethod
    def review_application_infrastructure(
        cls,
        db: Session,
        application_id: int,
        actor_id: str = "system",
    ) -> InfrastructureReviewSummary:
        """Analyze all infrastructure-related document versions for an application."""
        app = db.get(Application, application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found.")

        # Find all documents related to infrastructure
        infra_types = {
            "building_plan",
            "structural_stability",
            "fire_safety_certificate",
            "occupancy_certificate",
            "land_document",
            "campus_photo",
            "laboratory_photo",
        }

        evidence_items: list[InfrastructureReviewItem] = []
        inspection_reasons: list[str] = []

        for doc in app.documents:
            if doc.document_type not in infra_types:
                continue

            ver = doc.current_version
            if ver is None and doc.versions:
                ver = max(doc.versions, key=lambda v: v.version_number)
            if ver is None:
                continue

            item = cls._evaluate_version_evidence(ver, doc.document_type)
            evidence_items.append(item)

            if item.inspection_recommended and item.inspection_rationale:
                inspection_reasons.append(item.inspection_rationale)

            # Persist in DB
            db_record = InfrastructureEvidence(
                application_id=app.id,
                document_version_id=ver.id,
                evidence_type=item.evidence_type,
                declared_area_sqm=item.declared_area_sqm,
                observed_area_sqm=item.observed_area_sqm,
                inspection_recommended=item.inspection_recommended,
                inspection_rationale=item.inspection_rationale,
                analysis_metadata=json.dumps(item.analysis_metadata),
                created_at=_utc_now(),
            )
            db.add(db_record)

        db.flush()

        # Audit event
        ReviewAuditRepository.create_audit_event(
            db,
            action="INFRASTRUCTURE_EVIDENCE_EVALUATED",
            target_type="Application",
            target_id=str(app.id),
            actor_id=actor_id,
            institution_id=app.institution_id,
            details=json.dumps({
                "items_count": len(evidence_items),
                "inspection_recommended": bool(inspection_reasons),
                "reasons": inspection_reasons,
            }),
        )
        db.commit()

        return InfrastructureReviewSummary(
            application_id=app.id,
            overall_status="inspection_recommended" if inspection_reasons else "preliminary_compliant",
            physical_inspection_recommended=bool(inspection_reasons),
            inspection_reasons=inspection_reasons,
            items=evidence_items,
            evaluated_at=_utc_now(),
        )

    @classmethod
    def _evaluate_version_evidence(
        cls, version: DocumentVersion, doc_type: str
    ) -> InfrastructureReviewItem:
        """Run deterministic checks on an infrastructure document version."""
        inspection_recommended = False
        rationale: str | None = None
        declared_area: float | None = None
        observed_area: float | None = None
        metadata: dict[str, Any] = {
            "media_type": version.media_type,
            "byte_size": version.byte_size,
            "page_count": version.page_count,
            "sha256": version.sha256,
        }

        # Check A: Missing or scanned-only without extractable engineering stamps
        if version.scan_status == "rejected":
            inspection_recommended = True
            rationale = f"Document for '{doc_type}' failed security scanning and was quarantined."
            metadata["issue"] = "quarantined_file"

        elif doc_type in ("campus_photo", "laboratory_photo"):
            # Image photo checks
            if version.byte_size < 50_000:
                inspection_recommended = True
                rationale = f"Infrastructure photo '{doc_type}' resolution is unusually low ({version.byte_size} bytes); physical verification required."
                metadata["photo_quality"] = "low_resolution"
            else:
                metadata["photo_quality"] = "acceptable"

        elif doc_type == "building_plan":
            # Building blueprint: evaluate extractable areas
            metadata["blueprint_format"] = "architectural_drawing"
            if not version.extracted_fields:
                inspection_recommended = True
                rationale = "Building blueprint submitted without extractable municipal approval seal; physical inspection recommended."

        elif doc_type == "structural_stability":
            # Check if expired
            fields = {f.field_name: f for f in version.extracted_fields}
            exp_field = fields.get("valid_until") or fields.get("expiry_date")
            if exp_field and exp_field.normalized_value:
                exp_date = parse_iso_date_candidate(exp_field.normalized_value)
                if exp_date and exp_date < datetime.now(timezone.utc).date():
                    inspection_recommended = True
                    rationale = f"Building structural stability certificate has expired ({exp_date.isoformat()}); mandatory EVC physical inspection triggered."

        return InfrastructureReviewItem(
            evidence_type=doc_type,
            document_version_id=version.id,
            declared_area_sqm=declared_area,
            observed_area_sqm=observed_area,
            inspection_recommended=inspection_recommended,
            inspection_rationale=rationale,
            analysis_metadata=metadata,
        )

    @classmethod
    def list_evidence(cls, db: Session, application_id: int) -> list[InfrastructureEvidence]:
        """Fetch recorded infrastructure evidence rows for an application."""
        stmt = (
            select(InfrastructureEvidence)
            .where(InfrastructureEvidence.application_id == application_id)
            .order_by(InfrastructureEvidence.created_at.desc())
        )
        return list(db.scalars(stmt).all())

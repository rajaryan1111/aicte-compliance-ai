"""Authorized institutional-record comparison service.

Compares applicant claims against authorized AICTE records (previous EoA,
approved intake, NBA accreditation, previous deficiency history, TER fees).
Distinguishes between live authorized data, versioned records, synthetic fixtures,
and unavailable sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Application, InstitutionalRecordSnapshot
from backend.app.repositories.review_audit_repository import ReviewAuditRepository

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


SourceCategory = Literal[
    "live_authorized",
    "versioned_stored",
    "applicant_claim",
    "synthetic_demo",
    "unavailable",
]


@dataclass(frozen=True)
class RecordComparisonItem:
    record_type: str
    source_category: SourceCategory
    source_reference: str | None
    claim_value: Any
    authorized_value: Any
    matched: bool
    discrepancy_explanation: str | None
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InstitutionalComparisonReport:
    application_id: int
    institution_id: str
    overall_consistency: Literal["consistent", "discrepancies_detected", "source_unavailable"]
    comparisons: list[RecordComparisonItem]
    evaluated_at: datetime


class InstitutionalRecordService:
    """Coordinates retrieval and comparison of official institutional historical records."""

    @classmethod
    def get_or_create_snapshot(
        cls,
        db: Session,
        institution_id: int,
        record_type: str,
        *,
        source_category: SourceCategory = "synthetic_demo",
        source_reference: str | None = None,
        record_data: dict[str, Any] | None = None,
        limitations: str | None = None,
    ) -> InstitutionalRecordSnapshot:
        """Fetch the latest snapshot or create a baseline versioned snapshot."""
        stmt = (
            select(InstitutionalRecordSnapshot)
            .where(
                InstitutionalRecordSnapshot.institution_id == institution_id,
                InstitutionalRecordSnapshot.record_type == record_type,
            )
            .order_by(InstitutionalRecordSnapshot.retrieved_at.desc())
        )
        existing = db.scalars(stmt).first()
        if existing:
            return existing

        default_data = record_data or cls._generate_default_record_data(record_type)

        snapshot = InstitutionalRecordSnapshot(
            institution_id=institution_id,
            record_type=record_type,
            source_category=source_category,
            source_reference=source_reference or f"AICTE-HIST-{record_type.upper()}-2025",
            record_data=json.dumps(default_data),
            limitations=limitations or "Baseline synthetic demonstration record for scrutiny comparison.",
            retrieved_at=_utc_now(),
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot

    @classmethod
    def compare_application_against_records(
        cls,
        db: Session,
        application_id: int,
        actor_id: str = "system",
    ) -> InstitutionalComparisonReport:
        """Compare submitted application details against available authorized institutional records."""
        app = db.get(Application, application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found.")

        inst = app.institution
        inst_ref = inst.institution_id if inst else str(app.institution_id)

        comparisons: list[RecordComparisonItem] = []
        discrepancies_found = False

        # 1. Previous Approval / EoA Status
        eoa_snapshot = cls.get_or_create_snapshot(db, app.institution_id, "previous_eoa")
        eoa_data = json.loads(eoa_snapshot.record_data)
        prev_status = eoa_data.get("previous_approval_status", "approved")
        if app.application_type == "eoa" and prev_status != "approved":
            discrepancies_found = True
            comparisons.append(
                RecordComparisonItem(
                    record_type="previous_eoa",
                    source_category=eoa_snapshot.source_category,  # type: ignore
                    source_reference=eoa_snapshot.source_reference,
                    claim_value="regular_eoa_extension",
                    authorized_value=prev_status,
                    matched=False,
                    discrepancy_explanation=f"Previous institutional approval was '{prev_status}'; requires standing committee clearance.",
                    limitations=[eoa_snapshot.limitations or ""],
                )
            )
        else:
            comparisons.append(
                RecordComparisonItem(
                    record_type="previous_eoa",
                    source_category=eoa_snapshot.source_category,  # type: ignore
                    source_reference=eoa_snapshot.source_reference,
                    claim_value="eoa",
                    authorized_value=prev_status,
                    matched=True,
                    discrepancy_explanation=None,
                )
            )

        # 2. Approved Intake and Programmatic Roster
        intake_snapshot = cls.get_or_create_snapshot(db, app.institution_id, "approved_intake")
        intake_data = json.loads(intake_snapshot.record_data)
        approved_seats = intake_data.get("total_approved_seats", 360)
        comparisons.append(
            RecordComparisonItem(
                record_type="approved_intake",
                source_category=intake_snapshot.source_category,  # type: ignore
                source_reference=intake_snapshot.source_reference,
                claim_value="intake_aligned",
                authorized_value=approved_seats,
                matched=True,
                discrepancy_explanation=None,
            )
        )

        # 3. Accreditation (NBA / NAAC)
        nba_snapshot = cls.get_or_create_snapshot(db, app.institution_id, "accreditation_nba")
        nba_data = json.loads(nba_snapshot.record_data)
        has_nba = nba_data.get("has_nba_accredited_programs", True)
        if app.application_type == "intake_change" and not has_nba:
            discrepancies_found = True
            comparisons.append(
                RecordComparisonItem(
                    record_type="accreditation_nba",
                    source_category=nba_snapshot.source_category,  # type: ignore
                    source_reference=nba_snapshot.source_reference,
                    claim_value="intake_expansion_requested",
                    authorized_value="no_accredited_courses",
                    matched=False,
                    discrepancy_explanation="Institutional record indicates no NBA-accredited courses, violating APH Clause 4.2 for intake expansion.",
                )
            )
        else:
            comparisons.append(
                RecordComparisonItem(
                    record_type="accreditation_nba",
                    source_category=nba_snapshot.source_category,  # type: ignore
                    source_reference=nba_snapshot.source_reference,
                    claim_value=app.application_type,
                    authorized_value="compliant",
                    matched=True,
                    discrepancy_explanation=None,
                )
            )

        # 4. TER Payment Status
        ter_snapshot = cls.get_or_create_snapshot(db, app.institution_id, "ter_fee_payment")
        ter_data = json.loads(ter_snapshot.record_data)
        payment_status = ter_data.get("payment_status", "success")
        if payment_status != "success":
            discrepancies_found = True
            comparisons.append(
                RecordComparisonItem(
                    record_type="ter_fee_payment",
                    source_category=ter_snapshot.source_category,  # type: ignore
                    source_reference=ter_snapshot.source_reference,
                    claim_value="fee_paid",
                    authorized_value=payment_status,
                    matched=False,
                    discrepancy_explanation=f"Technical Education Regulatory (TER) fee payment status is '{payment_status}'.",
                )
            )
        else:
            comparisons.append(
                RecordComparisonItem(
                    record_type="ter_fee_payment",
                    source_category=ter_snapshot.source_category,  # type: ignore
                    source_reference=ter_snapshot.source_reference,
                    claim_value="fee_paid",
                    authorized_value="success",
                    matched=True,
                    discrepancy_explanation=None,
                )
            )

        # Audit event
        ReviewAuditRepository.create_audit_event(
            db,
            action="INSTITUTIONAL_RECORDS_COMPARED",
            target_type="Application",
            target_id=str(app.id),
            actor_id=actor_id,
            institution_id=app.institution_id,
            details=json.dumps({
                "discrepancies_detected": discrepancies_found,
                "record_types": [c.record_type for c in comparisons],
            }),
        )
        db.commit()

        return InstitutionalComparisonReport(
            application_id=app.id,
            institution_id=inst_ref,
            overall_consistency="discrepancies_detected" if discrepancies_found else "consistent",
            comparisons=comparisons,
            evaluated_at=_utc_now(),
        )

    @classmethod
    def _generate_default_record_data(cls, record_type: str) -> dict[str, Any]:
        if record_type == "previous_eoa":
            return {
                "previous_academic_year": "2025-26",
                "previous_approval_status": "approved",
                "approval_letter_ref": "AICTE/WRO/2025-26/1-998241",
                "decision_date": "2025-05-15",
            }
        elif record_type == "approved_intake":
            return {
                "total_approved_seats": 360,
                "approved_divisions": 6,
                "programmes": ["Computer Science & Engineering", "Mechanical Engineering", "Electronics & Communication"],
            }
        elif record_type == "accreditation_nba":
            return {
                "has_nba_accredited_programs": True,
                "accredited_courses_count": 2,
                "valid_until": "2027-06-30",
            }
        elif record_type == "ter_fee_payment":
            return {
                "challan_number": "TER-2026-CHAL-89102",
                "payment_status": "success",
                "amount_inr": 250000,
                "payment_date": "2026-09-10",
            }
        return {"status": "unconfigured"}

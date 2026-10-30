"""Validation orchestration service for application-level pre-scrutiny pipeline.

Coordinates:
- Verification of document processing and intake readiness.
- Selection of immutable eligible document-version snapshots.
- Source-governed rule catalog checks and explicit checklist selection.
- Deterministic preliminary checks (readiness, expiry, date order, cross-document consistency, duplicate files).
- Creation and persistence of reproducible ValidationRun, ValidationCheckResult, and Finding records.
- Attributable audit-event recording.

All outputs are strictly advisory. A successful run does not constitute official AICTE
approval, accreditation, or document authenticity verification.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Application,
    Document,
    DocumentVersion,
    Finding,
    ValidationCheckResult,
    ValidationRun,
)
from backend.app.ocr_adapter import parse_iso_date_candidate
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.repositories.validation_repository import ValidationRepository
from backend.app.rule_catalog import RuleRegistry

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.60

PRELIMINARY_ADVISORY_DISCLAIMER = (
    "Preliminary pre-scrutiny result only. This evaluation is advisory and based on "
    "deterministic checks against available observations. It does not constitute official "
    "AICTE regulatory approval, accreditation, institutional eligibility, or verification "
    "of document authenticity."
)

# Versioned synthetic demonstration checklists for controlled testing only.
# Clearly labelled as synthetic; never represented as official AICTE statutory rules.
SYNTHETIC_DEMO_CHECKLISTS: dict[str, list[str]] = {
    "eoa": ["land_document", "building_plan", "fire_safety_certificate"],
    "new_program": ["land_document", "building_plan", "structural_stability", "fire_safety_certificate"],
    "intake_change": ["land_document", "fire_safety_certificate"],
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ValidationOrchestrationService:
    """Orchestrates multi-document pre-scrutiny validation for an authorized application."""

    def __init__(
        self,
        rule_registry: RuleRegistry | None = None,
        load_aph_rules: bool = False,
    ) -> None:
        self.rule_registry = rule_registry or RuleRegistry()
        if load_aph_rules and len(self.rule_registry) == 0:
            from backend.app.services.rule_engine import RuleApprovalService
            RuleApprovalService.activate_standard_aph_rules(self.rule_registry)

    def run_validation(
        self,
        db: Session,
        application_id: int,
        *,
        actor_id: str | None = None,
        evaluation_date: date | None = None,
        checklist_type: str = "default",
        required_documents: list[str] | None = None,
        ruleset_version: str = "0.1.0-draft",
    ) -> ValidationRun:
        """Execute deterministic application validation checks and persist a reproducible run."""
        app = db.get(Application, application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found.")

        eval_date = evaluation_date or _utc_now().date()

        # Create initial run record
        run = ValidationRepository.create_run(
            db,
            application_id=application_id,
            evaluation_date=eval_date,
            ruleset_version=ruleset_version,
            status="running",
            triggered_by=actor_id or "system",
        )
        db.flush()

        try:
            return self.execute_validation_for_run(
                db,
                run=run,
                checklist_type=checklist_type,
                required_documents=required_documents,
                actor_id=actor_id,
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Error executing validation run %s: %s", run.id, exc)
            # Re-fetch run and record failure
            run_cur = ValidationRepository.get_run(db, run.id)
            if run_cur:
                ValidationRepository.update_run(
                    db,
                    run_cur,
                    status="failed",
                    completed_at=_utc_now(),
                    limitations=json.dumps([f"Execution error: {exc.__class__.__name__}"]),
                )
                db.commit()
                return run_cur
            raise exc

    def execute_validation_for_run(
        self,
        db: Session,
        run: ValidationRun,
        *,
        checklist_type: str = "default",
        required_documents: list[str] | None = None,
        actor_id: str | None = None,
    ) -> ValidationRun:
        """Internal execution logic populating check results, findings, and summary counts."""
        app = db.get(Application, run.application_id)
        if app is None:
            raise ValueError(f"Application {run.application_id} not found.")

        eval_date = run.evaluation_date
        limitations: list[str] = []

        # ----------------------------------------------------------------------
        # Stage 1: Document Version Snapshot & Processing Readiness
        # ----------------------------------------------------------------------
        eligible_versions: dict[str, DocumentVersion] = {}
        pending_versions: dict[str, DocumentVersion] = {}
        rejected_versions: dict[str, DocumentVersion] = {}
        failed_versions: dict[str, DocumentVersion] = {}

        # Query all logical document slots for this application
        docs_stmt = select(Document).where(Document.application_id == app.id)
        docs = list(db.scalars(docs_stmt).all())

        for doc in docs:
            # Use current_version or latest uploaded version
            version = doc.current_version
            if version is None and doc.versions:
                version = max(doc.versions, key=lambda v: v.version_number)

            if version is None:
                continue

            # Classify intake & security state
            if version.scan_status == "rejected" or version.processing_status == "rejected":
                rejected_versions[doc.document_type] = version
            elif (
                version.scan_status in ("pending_scan", "scan_unavailable")
                or version.processing_status in ("queued", "scanning", "extracting", "retry_wait")
            ):
                pending_versions[doc.document_type] = version
            elif version.processing_status == "failed":
                failed_versions[doc.document_type] = version
            elif version.scan_status == "clean" and version.processing_status in ("succeeded", "partial"):
                eligible_versions[doc.document_type] = version
            else:
                pending_versions[doc.document_type] = version

        # Snapshot the consumed eligible version IDs
        consumed_version_ids = sorted([v.id for v in eligible_versions.values()])

        # ----------------------------------------------------------------------
        # Stage 2: Checklist & Rule Provenance Gate
        # ----------------------------------------------------------------------
        rule_snapshot_data: dict[str, Any] = {
            "ruleset_version": run.ruleset_version,
            "checklist_type": checklist_type,
            "application_type": app.application_type,
            "academic_year": app.academic_year,
            "evaluation_date": eval_date.isoformat(),
        }

        # Check official regulatory rule catalogue
        from backend.app.services.rule_engine import RuleApprovalService
        db_approved_rules = RuleApprovalService.load_approved_rules_from_db(
            db, application_type=app.application_type, academic_year=app.academic_year
        )
        for r_draft in db_approved_rules:
            if self.rule_registry.get_active(r_draft.rule_id) is None:
                try:
                    self.rule_registry.activate(r_draft)
                except Exception:
                    pass

        active_official_rules = self.rule_registry.active_rules()
        app_year = app.academic_year.strip() if app.academic_year else ""
        year_variants = {app_year}
        if "-" in app_year:
            p1, p2 = app_year.split("-", 1)
            if len(p1) == 4 and len(p2) == 4:
                year_variants.add(f"{p1}-{p2[2:]}")
            elif len(p1) == 4 and len(p2) == 2:
                year_variants.add(f"{p1}-{p1[:2]}{p2}")

        applicable_rules = [
            r for r in active_official_rules
            if app.application_type in r.applicability.application_types
            and any(v in r.applicability.academic_years for v in year_variants)
        ]

        if not applicable_rules:
            reg_limitation = (
                f"No verified, approved and active AICTE rules found for application_type='{app.application_type}', "
                f"academic_year='{app.academic_year}'. Regulatory rule evaluation skipped."
            )
            limitations.append(reg_limitation)
            rule_snapshot_data["official_rules_active"] = False
        else:
            rule_snapshot_data["official_rules_active"] = True
            rule_snapshot_data["active_rule_ids"] = [r.rule_id for r in applicable_rules]

        # Determine target checklist
        target_checklist: list[str] = []
        if checklist_type == "caller_specified" and required_documents is not None:
            target_checklist = [d.strip() for d in required_documents if d.strip()]
            rule_snapshot_data["source"] = "caller_specified_checklist"
        elif checklist_type == "synthetic_demo":
            target_checklist = SYNTHETIC_DEMO_CHECKLISTS.get(app.application_type, ["land_document", "building_plan", "fire_safety_certificate"])
            rule_snapshot_data["source"] = "synthetic_demo_ruleset"
            limitations.append("Evaluated using synthetic demonstration checklist; not an official AICTE mandate.")
        else:
            rule_snapshot_data["source"] = "unconfigured_default"
            limitations.append("Universal document checklist not configured; no active AICTE checklist available.")

        # ----------------------------------------------------------------------
        # Stage 3: Deterministic Evaluation Checks
        # ----------------------------------------------------------------------
        check_results: list[ValidationCheckResult] = []
        findings: list[Finding] = []

        # Check A: Document Readiness & Completeness
        if target_checklist:
            for req_doc in target_checklist:
                if req_doc in rejected_versions:
                    rej_v = rejected_versions[req_doc]
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_DOCUMENT_READINESS",
                        check_name="Document Intake & Security Gate",
                        category="document_readiness",
                        status="failed",
                        document_version_id=rej_v.id,
                        message=f"Document '{req_doc}' was rejected by malware security policy and cannot be evaluated.",
                        evidence=json.dumps({"document_type": req_doc, "scan_status": rej_v.scan_status}),
                    )
                    check_results.append(cr)
                    f = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=rej_v.id,
                        code="MALWARE_SCAN_REJECTED",
                        severity="error",
                        summary=f"Document '{req_doc}' failed security scanning and remains quarantined.",
                        evidence=json.dumps({"document_type": req_doc, "scan_status": rej_v.scan_status}),
                    )
                    findings.append(f)

                elif req_doc in pending_versions:
                    pend_v = pending_versions[req_doc]
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_DOCUMENT_READINESS",
                        check_name="Document Intake & Security Gate",
                        category="document_readiness",
                        status="inconclusive",
                        document_version_id=pend_v.id,
                        message=f"Document '{req_doc}' is currently being processed (status: {pend_v.processing_status}, scan: {pend_v.scan_status}).",
                        evidence=json.dumps({"document_type": req_doc, "processing_status": pend_v.processing_status}),
                    )
                    check_results.append(cr)
                    f = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=pend_v.id,
                        code="DOCUMENT_PROCESSING_PENDING",
                        severity="warning",
                        summary=f"Document '{req_doc}' is awaiting completion of background scanning and OCR.",
                        evidence=json.dumps({"document_type": req_doc, "processing_status": pend_v.processing_status}),
                    )
                    findings.append(f)

                elif req_doc in failed_versions:
                    fail_v = failed_versions[req_doc]
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_DOCUMENT_READINESS",
                        check_name="Document Intake & Security Gate",
                        category="document_readiness",
                        status="failed",
                        document_version_id=fail_v.id,
                        message=f"Document '{req_doc}' processing failed during extraction.",
                        evidence=json.dumps({"document_type": req_doc, "processing_status": "failed"}),
                    )
                    check_results.append(cr)
                    f = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=fail_v.id,
                        code="DOCUMENT_PROCESSING_FAILED",
                        severity="error",
                        summary=f"Document '{req_doc}' processing encountered a fatal error.",
                        evidence=json.dumps({"document_type": req_doc}),
                    )
                    findings.append(f)

                elif req_doc in eligible_versions:
                    elig_v = eligible_versions[req_doc]
                    if not elig_v.extracted_fields:
                        cr = ValidationRepository.create_check_result(
                            db,
                            validation_run_id=run.id,
                            check_id="CHECK_DOCUMENT_READINESS",
                            check_name="Document Intake & Security Gate",
                            category="document_readiness",
                            status="inconclusive",
                            document_version_id=elig_v.id,
                            message=f"Document '{req_doc}' was scanned cleanly but yielded no extractable text or observations.",
                            evidence=json.dumps({"document_type": req_doc, "extracted_fields": 0}),
                        )
                        check_results.append(cr)
                        f = ValidationRepository.create_finding(
                            db,
                            validation_run_id=run.id,
                            document_version_id=elig_v.id,
                            code="NO_EXTRACTABLE_TEXT",
                            severity="warning",
                            summary=f"Document '{req_doc}' contains no machine-extractable text.",
                            evidence=json.dumps({"document_type": req_doc}),
                        )
                        findings.append(f)
                    else:
                        cr = ValidationRepository.create_check_result(
                            db,
                            validation_run_id=run.id,
                            check_id="CHECK_DOCUMENT_READINESS",
                            check_name="Document Intake & Security Gate",
                            category="document_readiness",
                            status="passed",
                            document_version_id=elig_v.id,
                            message=f"Document '{req_doc}' is verified, clean, and processed.",
                            evidence=json.dumps({"document_type": req_doc, "fields_count": len(elig_v.extracted_fields)}),
                        )
                        check_results.append(cr)

                else:
                    # Missing document
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_DOCUMENT_READINESS",
                        check_name="Document Intake & Security Gate",
                        category="document_readiness",
                        status="failed",
                        document_version_id=None,
                        message=f"Required document '{req_doc}' has not been uploaded for this application.",
                        evidence=json.dumps({"missing_document": req_doc}),
                    )
                    check_results.append(cr)
                    f = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=None,
                        code="MISSING_DOCUMENT",
                        severity="error",
                        summary=f"Required document '{req_doc}' was not submitted.",
                        evidence=json.dumps({"source": "configured_checklist", "observed": "not_submitted", "document_type": req_doc}),
                    )
                    findings.append(f)
        else:
            # No checklist configured
            cr = ValidationRepository.create_check_result(
                db,
                validation_run_id=run.id,
                check_id="CHECK_DOCUMENT_READINESS",
                check_name="Document Intake & Security Gate",
                category="document_readiness",
                status="not_run",
                document_version_id=None,
                message="Universal document checklist not configured; no active AICTE checklist available.",
            )
            check_results.append(cr)

        # Check B: Document Expiry Checks
        for doc_type, ver in eligible_versions.items():
            fields_map = {f.field_name: f for f in ver.extracted_fields}
            expiry_field = fields_map.get("valid_until") or fields_map.get("expiry_date")

            if expiry_field and expiry_field.normalized_value:
                parsed_expiry = parse_iso_date_candidate(expiry_field.normalized_value)
                if parsed_expiry is not None:
                    if parsed_expiry < eval_date:
                        cr = ValidationRepository.create_check_result(
                            db,
                            validation_run_id=run.id,
                            check_id="CHECK_DOCUMENT_EXPIRY",
                            check_name="Document Expiry Date Check",
                            category="validity",
                            status="failed",
                            document_version_id=ver.id,
                            message=f"Document '{doc_type}' expiry date {parsed_expiry.isoformat()} is before evaluation date {eval_date.isoformat()}.",
                            evidence=json.dumps({
                                "document_type": doc_type,
                                "expiry_date": parsed_expiry.isoformat(),
                                "evaluation_date": eval_date.isoformat(),
                                "field_name": expiry_field.field_name,
                            }),
                        )
                        check_results.append(cr)
                        f = ValidationRepository.create_finding(
                            db,
                            validation_run_id=run.id,
                            document_version_id=ver.id,
                            code="DOCUMENT_EXPIRED",
                            severity="error",
                            summary=f"Document '{doc_type}' expired on {parsed_expiry.isoformat()} (prior to evaluation date {eval_date.isoformat()}).",
                            evidence=json.dumps({
                                "document_type": doc_type,
                                "expiry_date": parsed_expiry.isoformat(),
                                "evaluation_date": eval_date.isoformat(),
                            }),
                        )
                        findings.append(f)
                    else:
                        cr = ValidationRepository.create_check_result(
                            db,
                            validation_run_id=run.id,
                            check_id="CHECK_DOCUMENT_EXPIRY",
                            check_name="Document Expiry Date Check",
                            category="validity",
                            status="passed",
                            document_version_id=ver.id,
                            message=f"Document '{doc_type}' is valid until {parsed_expiry.isoformat()} (on or after {eval_date.isoformat()}).",
                            evidence=json.dumps({
                                "document_type": doc_type,
                                "expiry_date": parsed_expiry.isoformat(),
                                "evaluation_date": eval_date.isoformat(),
                            }),
                        )
                        check_results.append(cr)
                else:
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_DOCUMENT_EXPIRY",
                        check_name="Document Expiry Date Check",
                        category="validity",
                        status="inconclusive",
                        document_version_id=ver.id,
                        message=f"Document '{doc_type}' has expiry field '{expiry_field.raw_text}' that could not be parsed as a valid ISO date.",
                    )
                    check_results.append(cr)
            else:
                cr = ValidationRepository.create_check_result(
                    db,
                    validation_run_id=run.id,
                    check_id="CHECK_DOCUMENT_EXPIRY",
                    check_name="Document Expiry Date Check",
                    category="validity",
                    status="not_applicable",
                    document_version_id=ver.id,
                    message=f"Document '{doc_type}' does not contain an extracted expiry date.",
                )
                check_results.append(cr)

        # Check C: Date Order Consistency (issue_date vs valid_until)
        for doc_type, ver in eligible_versions.items():
            fields_map = {f.field_name: f for f in ver.extracted_fields}
            issue_f = fields_map.get("issue_date")
            valid_f = fields_map.get("valid_until")

            if issue_f and valid_f and issue_f.normalized_value and valid_f.normalized_value:
                issue_d = parse_iso_date_candidate(issue_f.normalized_value)
                valid_d = parse_iso_date_candidate(valid_f.normalized_value)
                if issue_d and valid_d:
                    if issue_d > valid_d:
                        cr = ValidationRepository.create_check_result(
                            db,
                            validation_run_id=run.id,
                            check_id="CHECK_DATE_ORDER",
                            check_name="Chronological Date Order Consistency",
                            category="consistency",
                            status="failed",
                            document_version_id=ver.id,
                            message=f"Document '{doc_type}' issue date {issue_d.isoformat()} is after expiry date {valid_d.isoformat()}.",
                            evidence=json.dumps({"issue_date": issue_d.isoformat(), "valid_until": valid_d.isoformat()}),
                        )
                        check_results.append(cr)
                        f = ValidationRepository.create_finding(
                            db,
                            validation_run_id=run.id,
                            document_version_id=ver.id,
                            code="INVALID_DATE_ORDER",
                            severity="error",
                            summary=f"Document '{doc_type}' issue date {issue_d.isoformat()} is after expiry date {valid_d.isoformat()}.",
                            evidence=json.dumps({"issue_date": issue_d.isoformat(), "valid_until": valid_d.isoformat()}),
                        )
                        findings.append(f)
                    else:
                        cr = ValidationRepository.create_check_result(
                            db,
                            validation_run_id=run.id,
                            check_id="CHECK_DATE_ORDER",
                            check_name="Chronological Date Order Consistency",
                            category="consistency",
                            status="passed",
                            document_version_id=ver.id,
                            message=f"Document '{doc_type}' issue date {issue_d.isoformat()} precedes expiry date {valid_d.isoformat()}.",
                        )
                        check_results.append(cr)

        # Check D: Institution Identifier Consistency
        inst_id_expected = app.institution.institution_id if app.institution else str(app.institution_id)
        for doc_type, ver in eligible_versions.items():
            fields_map = {f.field_name: f for f in ver.extracted_fields}
            extracted_inst = (
                fields_map.get("institution_id")
                or fields_map.get("institution_name")
                or fields_map.get("application_reference")
            )
            if extracted_inst and extracted_inst.normalized_value:
                obs_val = extracted_inst.normalized_value.strip()
                if obs_val.lower() != inst_id_expected.strip().lower():
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_INSTITUTION_CONSISTENCY",
                        check_name="Institutional Identity Consistency",
                        category="identity",
                        status="failed",
                        document_version_id=ver.id,
                        message=f"Extracted institution identifier '{obs_val}' in '{doc_type}' conflicts with application institution '{inst_id_expected}'.",
                        evidence=json.dumps({"extracted": obs_val, "expected": inst_id_expected, "document_type": doc_type}),
                    )
                    check_results.append(cr)
                    f = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=ver.id,
                        code="INSTITUTION_MISMATCH",
                        severity="warning",
                        summary=f"Extracted institution identifier '{obs_val}' does not match expected '{inst_id_expected}'.",
                        evidence=json.dumps({"extracted": obs_val, "expected": inst_id_expected, "document_type": doc_type}),
                    )
                    findings.append(f)
                else:
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_INSTITUTION_CONSISTENCY",
                        check_name="Institutional Identity Consistency",
                        category="identity",
                        status="passed",
                        document_version_id=ver.id,
                        message=f"Document '{doc_type}' matches expected institution '{inst_id_expected}'.",
                    )
                    check_results.append(cr)

        # Check E: Cross-Document Field Consistency (conflicting values across documents)
        extracted_names: dict[str, tuple[str, DocumentVersion]] = {}
        for doc_type, ver in eligible_versions.items():
            fields_map = {f.field_name: f for f in ver.extracted_fields}
            inst_f = fields_map.get("institution_name")
            if inst_f and inst_f.normalized_value:
                extracted_names[doc_type] = (inst_f.normalized_value.strip().lower(), ver)

        if len(extracted_names) >= 2:
            unique_names = {v[0] for v in extracted_names.values()}
            if len(unique_names) > 1:
                conflict_details = {k: v[0] for k, v in extracted_names.items()}
                cr = ValidationRepository.create_check_result(
                    db,
                    validation_run_id=run.id,
                    check_id="CHECK_CROSS_DOCUMENT_CONSISTENCY",
                    check_name="Cross-Document Observation Consistency",
                    category="consistency",
                    status="failed",
                    document_version_id=None,
                    message=f"Conflicting institution names extracted across documents: {conflict_details}",
                    evidence=json.dumps(conflict_details),
                )
                check_results.append(cr)
                f = ValidationRepository.create_finding(
                    db,
                    validation_run_id=run.id,
                    document_version_id=None,
                    code="INCONSISTENT_DOCUMENT_FIELDS",
                    severity="warning",
                    summary="Conflicting normalized values extracted across multiple submitted documents.",
                    evidence=json.dumps(conflict_details),
                )
                findings.append(f)
            else:
                cr = ValidationRepository.create_check_result(
                    db,
                    validation_run_id=run.id,
                    check_id="CHECK_CROSS_DOCUMENT_CONSISTENCY",
                    check_name="Cross-Document Observation Consistency",
                    category="consistency",
                    status="passed",
                    document_version_id=None,
                    message="Extracted institutional names are consistent across all submitted documents.",
                )
                check_results.append(cr)
        else:
            cr = ValidationRepository.create_check_result(
                db,
                validation_run_id=run.id,
                check_id="CHECK_CROSS_DOCUMENT_CONSISTENCY",
                check_name="Cross-Document Observation Consistency",
                category="consistency",
                status="not_applicable",
                document_version_id=None,
                message="Fewer than two documents with comparable extracted fields were available.",
            )
            check_results.append(cr)

        # Check F: Duplicate Document Indicators (SHA-256 reuse across distinct slots)
        hashes_seen: dict[str, list[tuple[str, DocumentVersion]]] = {}
        for doc in docs:
            ver = doc.current_version or (max(doc.versions, key=lambda v: v.version_number) if doc.versions else None)
            if ver and ver.sha256:
                hashes_seen.setdefault(ver.sha256, []).append((doc.document_type, ver))

        duplicates_found = False
        for sha, occurrences in hashes_seen.items():
            if len(occurrences) > 1:
                duplicates_found = True
                slots = [occ[0] for occ in occurrences]
                for occ_slot, occ_ver in occurrences:
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_DUPLICATE_FILES",
                        check_name="File Content Provenance & Duplicate Detection",
                        category="provenance",
                        status="failed",
                        document_version_id=occ_ver.id,
                        message=f"Identical file content (SHA-256: {sha[:16]}...) was submitted for multiple document slots: {slots}.",
                        evidence=json.dumps({"sha256": sha, "slots": slots}),
                    )
                    check_results.append(cr)
                    f = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=occ_ver.id,
                        code="DUPLICATE_FILE_INDICATOR",
                        severity="warning",
                        summary=f"Identical file content submitted for slots {slots}; human review recommended.",
                        evidence=json.dumps({"sha256": sha, "shared_slots": slots}),
                    )
                    findings.append(f)

        if not duplicates_found:
            cr = ValidationRepository.create_check_result(
                db,
                validation_run_id=run.id,
                check_id="CHECK_DUPLICATE_FILES",
                check_name="File Content Provenance & Duplicate Detection",
                category="provenance",
                status="passed",
                document_version_id=None,
                message="No duplicate file hashes detected across document slots.",
            )
            check_results.append(cr)

        # Check G: Extraction Confidence Review
        low_confidence_found = False
        for doc_type, ver in eligible_versions.items():
            for f_obs in ver.extracted_fields:
                if f_obs.confidence is not None and f_obs.confidence < LOW_CONFIDENCE_THRESHOLD:
                    low_confidence_found = True
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_EXTRACTION_CONFIDENCE",
                        check_name="Extraction Confidence Review",
                        category="confidence",
                        status="inconclusive",
                        document_version_id=ver.id,
                        message=f"Field '{f_obs.field_name}' in '{doc_type}' has confidence {f_obs.confidence:.2f} (below {LOW_CONFIDENCE_THRESHOLD:.2f}).",
                        evidence=json.dumps({"field_name": f_obs.field_name, "confidence": f_obs.confidence}),
                    )
                    check_results.append(cr)
                    f = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=ver.id,
                        code="LOW_CONFIDENCE_EXTRACTION",
                        severity="warning",
                        summary=f"Extracted field '{f_obs.field_name}' in '{doc_type}' requires human review due to low extraction confidence.",
                        evidence=json.dumps({"field_name": f_obs.field_name, "confidence": f_obs.confidence}),
                    )
                    findings.append(f)

        if not low_confidence_found and eligible_versions:
            cr = ValidationRepository.create_check_result(
                db,
                validation_run_id=run.id,
                check_id="CHECK_EXTRACTION_CONFIDENCE",
                check_name="Extraction Confidence Review",
                category="confidence",
                status="passed",
                document_version_id=None,
                message="All extracted observations meet or exceed the confidence review threshold.",
            )
            check_results.append(cr)

        # Check F2: Cross-Institution Hash Provenance Check
        cross_app_collision = False
        for doc_type_f2, ver_f2 in eligible_versions.items():
            if ver_f2.sha256:
                other_apps_stmt = (
                    select(Application)
                    .join(Document, Document.application_id == Application.id)
                    .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                    .where(
                        DocumentVersion.sha256 == ver_f2.sha256,
                        Application.institution_id != app.institution_id,
                    )
                )
                other_apps = list(db.scalars(other_apps_stmt).all())
                if other_apps:
                    cross_app_collision = True
                    other_inst_ids = sorted({str(oa.institution_id) for oa in other_apps})
                    cr = ValidationRepository.create_check_result(
                        db,
                        validation_run_id=run.id,
                        check_id="CHECK_CROSS_APPLICATION_DUPLICATES",
                        check_name="Cross-Institution Hash Provenance Check",
                        category="provenance",
                        status="failed",
                        document_version_id=ver_f2.id,
                        message=f"Document '{doc_type_f2}' has identical hash to document submitted by other institution(s): {other_inst_ids}.",
                        evidence=json.dumps({"sha256": ver_f2.sha256, "conflicting_institutions": other_inst_ids}),
                    )
                    check_results.append(cr)
                    f = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=ver_f2.id,
                        code="CROSS_INSTITUTION_HASH_COLLISION",
                        severity="warning",
                        summary=f"Document '{doc_type_f2}' matches file submitted by another institution; potential unauthorized document reuse.",
                        evidence=json.dumps({"sha256": ver_f2.sha256, "institutions": other_inst_ids}),
                    )
                    findings.append(f)
        if not cross_app_collision and eligible_versions:
            cr = ValidationRepository.create_check_result(
                db,
                validation_run_id=run.id,
                check_id="CHECK_CROSS_APPLICATION_DUPLICATES",
                check_name="Cross-Institution Hash Provenance Check",
                category="provenance",
                status="passed",
                document_version_id=None,
                message="No cross-institution document hash collisions detected.",
            )
            check_results.append(cr)

        # Check H: Statutory AICTE Rules Check
        if not applicable_rules:
            cr_statutory = ValidationRepository.create_check_result(
                db,
                validation_run_id=run.id,
                check_id="CHECK_OFFICIAL_REGULATORY_RULES",
                check_name="Statutory Regulatory Compliance Gate",
                category="regulatory",
                status="not_run",
                document_version_id=None,
                message="No active, approved statutory rules in registry for this cycle.",
                limitations=json.dumps(limitations),
            )
            check_results.append(cr_statutory)
        else:
            from backend.app.services.rule_engine import RuleEngineService, RuleEvaluationContext
            rule_svc = RuleEngineService(self.rule_registry)
            eval_ctx = RuleEvaluationContext(
                application_id=app.id,
                application_type=app.application_type,
                academic_year=app.academic_year,
                institution_id=app.institution.institution_id if app.institution else str(app.institution_id),
                evaluation_date=eval_date,
                eligible_versions=eligible_versions,
            )
            rule_eval_results = rule_svc.evaluate_rules(eval_ctx)
            for r_res in rule_eval_results:
                cr_rule = ValidationRepository.create_check_result(
                    db,
                    validation_run_id=run.id,
                    check_id=f"RULE_{r_res.rule_id}",
                    check_name=f"{r_res.rule_id} ({r_res.clause_citation})",
                    category="regulatory",
                    status=r_res.status if r_res.status in ("passed", "failed", "inconclusive", "not_applicable", "not_run") else "inconclusive",
                    document_version_id=r_res.document_version_id,
                    message=r_res.message,
                    evidence=json.dumps(r_res.evidence),
                    limitations=json.dumps(r_res.limitations) if r_res.limitations else None,
                )
                check_results.append(cr_rule)

                if r_res.status in ("failed", "inconclusive", "trigger_unevaluable"):
                    f_rule = ValidationRepository.create_finding(
                        db,
                        validation_run_id=run.id,
                        document_version_id=r_res.document_version_id,
                        code=f"REGULATORY_DEFICIENCY_{r_res.rule_id}",
                        severity=r_res.severity,
                        summary=r_res.message,
                        evidence=json.dumps(r_res.evidence),
                    )
                    findings.append(f_rule)

        # ----------------------------------------------------------------------
        # Stage 4: Summary Counts and Outcome Synthesis
        # ----------------------------------------------------------------------
        counts = {
            "passed": sum(1 for c in check_results if c.status == "passed"),
            "failed": sum(1 for c in check_results if c.status == "failed"),
            "inconclusive": sum(1 for c in check_results if c.status == "inconclusive"),
            "not_applicable": sum(1 for c in check_results if c.status == "not_applicable"),
            "not_run": sum(1 for c in check_results if c.status == "not_run"),
        }

        # Determine preliminary high-level outcome
        if pending_versions:
            outcome = "processing_incomplete"
        elif counts["failed"] > 0 or findings:
            outcome = "attention_required"
        elif counts["inconclusive"] > 0:
            outcome = "inconclusive"
        elif counts["passed"] > 0:
            outcome = "preliminary_checks_passed"
        else:
            outcome = "inconclusive"

        # Finalize and persist run record
        run = ValidationRepository.update_run(
            db,
            run,
            status="succeeded",
            outcome=outcome,
            completed_at=_utc_now(),
            consumed_version_ids=json.dumps(consumed_version_ids),
            rule_snapshot=json.dumps(rule_snapshot_data),
            summary_counts=json.dumps(counts),
            limitations=json.dumps(limitations),
        )

        ReviewAuditRepository.create_audit_event(
            db,
            action="VALIDATION_RUN_COMPLETED",
            target_type="ValidationRun",
            target_id=str(run.id),
            actor_id=actor_id or "system",
            institution_id=app.institution_id,
            details=json.dumps({
                "outcome": outcome,
                "counts": counts,
                "findings_count": len(findings),
                "consumed_versions": consumed_version_ids,
            }),
        )
        db.commit()
        db.refresh(run)
        return run

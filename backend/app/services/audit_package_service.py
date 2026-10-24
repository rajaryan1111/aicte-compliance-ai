"""Service layer for exportable audit package generation, tamper-evidence, and verification."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import logging
from typing import Any
import uuid
import zipfile

from sqlalchemy.orm import Session

from backend.app.core.storage import (
    StorageError,
    generate_storage_key,
    get_storage_backend,
)
from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    Finding,
    ReviewAction,
    User,
    ValidationCheckResult,
    ValidationRun,
)
from backend.app.repositories.audit_package_repository import AuditPackageRepository
from backend.app.schemas.audit_package import (
    AuditPackageCreateRequest,
    AuditPackageDetailRead,
    AuditPackageItemManifest,
    AuditPackageListResponse,
    AuditPackageManifest,
    AuditPackageRead,
    AuditPackageVerificationResponse,
)

logger = logging.getLogger(__name__)

ADVISORY_DISCLAIMER = (
    "Advisory audit package only. Pre-scrutiny observations, evidence manifests, "
    "and human review actions do not constitute official statutory AICTE approval or rejection."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditPackageError(Exception):
    """Base exception for audit package operations."""


class AuditPackageNotFoundError(AuditPackageError):
    """Raised when an audit package is not found."""


class AuditPackageService:
    """Coordinates immutable audit package bundling, cryptographic hashing, and hand-off."""

    @classmethod
    def create_package(
        cls,
        db: Session,
        *,
        application_id: int,
        user: User,
        payload: AuditPackageCreateRequest,
    ) -> AuditPackageDetailRead:
        """Generate and securely persist a tamper-evident audit package archive."""
        app = db.get(Application, application_id)
        if app is None:
            raise AuditPackageNotFoundError(f"Application {application_id} not found.")

        # Determine validation run
        if payload.validation_run_id is not None:
            run = db.get(ValidationRun, payload.validation_run_id)
            if run is None or run.application_id != application_id:
                raise AuditPackageNotFoundError(
                    f"Validation run {payload.validation_run_id} not found on application {application_id}."
                )
        else:
            # Pick latest completed run or latest run
            run = (
                db.query(ValidationRun)
                .filter(ValidationRun.application_id == application_id)
                .order_by(ValidationRun.id.desc())
                .first()
            )

        run_id = run.id if run else None
        now = _utc_now()
        package_ref = f"PKG-{app.institution.institution_id if app.institution else 'INST'}-APP{app.id}-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        pkg_name = payload.package_name or f"AuditPackage_{app.id}_{now.strftime('%Y%m%d')}"

        # ----------------------------------------------------------------------
        # 1. Assemble Scrutiny Report and Validation Outcomes
        # ----------------------------------------------------------------------
        report_data: dict[str, Any] = {
            "application_id": app.id,
            "institution_id": app.institution.institution_id if app.institution else str(app.institution_id),
            "academic_year": app.academic_year,
            "application_type": app.application_type,
            "application_status": app.status,
            "validation_run": None,
            "checks": [],
            "advisory_notice": ADVISORY_DISCLAIMER,
        }

        if run:
            report_data["validation_run"] = {
                "id": run.id,
                "status": run.status,
                "outcome": run.outcome,
                "evaluation_date": run.evaluation_date.isoformat() if run.evaluation_date else None,
                "ruleset_version": run.ruleset_version,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "summary_counts": run.summary_counts,
                "limitations": run.limitations,
            }
            checks = db.query(ValidationCheckResult).filter_by(validation_run_id=run.id).all()
            report_data["checks"] = [
                {
                    "check_id": c.check_id,
                    "check_name": c.check_name,
                    "category": c.category,
                    "status": c.status,
                    "message": c.message,
                    "evidence": c.evidence,
                    "limitations": c.limitations,
                }
                for c in checks
            ]

        # ----------------------------------------------------------------------
        # 2. Assemble Findings and Human Review Dispositions
        # ----------------------------------------------------------------------
        findings_query = db.query(Finding)
        if run:
            findings_query = findings_query.filter(Finding.validation_run_id == run.id)
        findings = findings_query.all()

        findings_data = [
            {
                "id": f.id,
                "validation_run_id": f.validation_run_id,
                "code": f.code,
                "automated_status": "observed_gap",
                "human_review_status": f.status,
                "severity": f.severity,
                "summary": f.summary,
                "evidence": f.evidence,
                "resolution_rationale": f.resolution_rationale,
                "resolved_by": f.resolved_by,
                "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
                "version": f.version,
            }
            for f in findings
        ]

        # ----------------------------------------------------------------------
        # 3. Assemble Immutable Human Review Actions Trail
        # ----------------------------------------------------------------------
        actions = (
            db.query(ReviewAction)
            .filter(ReviewAction.application_id == app.id)
            .order_by(ReviewAction.id.asc())
            .all()
        )
        review_actions_data = [
            {
                "id": a.id,
                "finding_id": a.finding_id,
                "validation_run_id": a.validation_run_id,
                "reviewer_id": a.reviewer_id,
                "actor_role": a.actor_role,
                "action": a.action,
                "previous_status": a.previous_status,
                "new_status": a.new_status,
                "comment": a.comment,
                "rationale": a.rationale,
                "request_id": a.request_id,
                "evidence_ref": a.evidence_ref,
                "metadata_payload": a.metadata_payload,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions
        ]

        # ----------------------------------------------------------------------
        # 4. Assemble Attributable Audit Log Trail
        # ----------------------------------------------------------------------
        audit_events = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.target_type.in_(["Application", "Finding", "ValidationRun", "ReviewAction"]),
                AuditEvent.target_id.in_([str(app.id)] + [str(f.id) for f in findings]),
            )
            .order_by(AuditEvent.id.asc())
            .all()
        )
        audit_trail_data = [
            {
                "id": ev.id,
                "actor_id": ev.actor_id,
                "action": ev.action,
                "target_type": ev.target_type,
                "target_id": ev.target_id,
                "request_id": ev.request_id,
                "details": ev.details,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
            for ev in audit_events
        ]

        # ----------------------------------------------------------------------
        # 5. Collect Evidence Document Files (if requested)
        # ----------------------------------------------------------------------
        file_entries: dict[str, bytes] = {}

        if payload.include_documents:
            storage = get_storage_backend()
            doc_versions = (
                db.query(DocumentVersion)
                .join(Document, DocumentVersion.document_id == Document.id)
                .filter(Document.application_id == app.id)
                .all()
            )
            for dv in doc_versions:
                try:
                    if dv.storage_key and storage.exists(dv.storage_key):
                        doc_bytes = storage.read(dv.storage_key)
                        doc_name = dv.file_name or f"document_{dv.id}.pdf"
                        doc_path = f"documents/{dv.document.document_type}/{doc_name}"
                        file_entries[doc_path] = doc_bytes
                except StorageError as exc:
                    logger.warning("Could not read document version %s for audit package: %s", dv.id, exc)

        # Encode JSON data files
        file_entries["scrutiny_report.json"] = json.dumps(report_data, indent=2, sort_keys=True).encode("utf-8")
        file_entries["findings_resolution.json"] = json.dumps(findings_data, indent=2, sort_keys=True).encode("utf-8")
        file_entries["review_history.json"] = json.dumps(review_actions_data, indent=2, sort_keys=True).encode("utf-8")
        file_entries["audit_trail.json"] = json.dumps(audit_trail_data, indent=2, sort_keys=True).encode("utf-8")

        # ----------------------------------------------------------------------
        # 6. Calculate Cryptographic Item Checksums & Chained Root Hash
        # ----------------------------------------------------------------------
        manifest_items: list[AuditPackageItemManifest] = []
        checksum_lines: list[str] = []

        # Sort files deterministically
        for path in sorted(file_entries.keys()):
            data_bytes = file_entries[path]
            file_sha256 = hashlib.sha256(data_bytes).hexdigest()
            content_type = "application/json" if path.endswith(".json") else "application/octet-stream"
            manifest_items.append(
                AuditPackageItemManifest(
                    path=path,
                    sha256=file_sha256,
                    byte_size=len(data_bytes),
                    content_type=content_type,
                )
            )
            checksum_lines.append(f"{file_sha256}  {path}")

        checksums_content = "\n".join(checksum_lines) + "\n"
        checksums_bytes = checksums_content.encode("utf-8")
        file_entries["CHECKSUMS.txt"] = checksums_bytes

        # Root hash is the deterministic SHA-256 of the canonical CHECKSUMS.txt
        sha256_root_hash = hashlib.sha256(checksums_bytes).hexdigest()

        # Build Manifest JSON
        manifest = AuditPackageManifest(
            package_reference=package_ref,
            application_id=app.id,
            institution_id=app.institution.institution_id if app.institution else str(app.institution_id),
            academic_year=app.academic_year,
            application_type=app.application_type,
            validation_run_id=run_id,
            sha256_root_hash=sha256_root_hash,
            generated_at=now,
            generated_by=user.username,
            advisory_notice=ADVISORY_DISCLAIMER,
            items=manifest_items,
        )
        manifest_json_str = manifest.model_dump_json(indent=2)
        file_entries["manifest.json"] = manifest_json_str.encode("utf-8")

        # ----------------------------------------------------------------------
        # 7. Construct In-Memory ZIP Archive
        # ----------------------------------------------------------------------
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(file_entries.keys()):
                zf.writestr(path, file_entries[path])

        zip_bytes = zip_buffer.getvalue()

        # ----------------------------------------------------------------------
        # 8. Persist ZIP in Secure Private Storage
        # ----------------------------------------------------------------------
        storage_key = generate_storage_key(sha256=sha256_root_hash, extension="zip")
        storage = get_storage_backend()
        storage.put(storage_key, zip_bytes)

        # ----------------------------------------------------------------------
        # 9. Record Database Row and Attributable Audit Log
        # ----------------------------------------------------------------------
        package_row = AuditPackageRepository.create_package(
            db,
            package_reference=package_ref,
            application_id=app.id,
            validation_run_id=run_id,
            package_name=pkg_name,
            status="completed",
            sha256_root_hash=sha256_root_hash,
            file_size_bytes=len(zip_bytes),
            storage_key=storage_key,
            manifest_json=manifest_json_str,
            generated_by=user.username,
        )

        AuditPackageRepository.record_audit_event(
            db,
            actor_id=user.username,
            institution_id=app.institution_id,
            action="AUDIT_PACKAGE_CREATED",
            target_type="Application",
            target_id=str(app.id),
            details=f"Generated tamper-evident audit package {package_ref} with root hash {sha256_root_hash[:16]}...",
        )

        read_model = AuditPackageRead.model_validate(package_row)
        return AuditPackageDetailRead(
            **read_model.model_dump(),
            manifest=manifest,
        )

    @classmethod
    def get_package(
        cls,
        db: Session,
        *,
        application_id: int,
        package_id: int,
    ) -> AuditPackageDetailRead:
        """Retrieve single audit package with embedded manifest."""
        pkg = AuditPackageRepository.get_by_id(db, application_id=application_id, package_id=package_id)
        if pkg is None:
            raise AuditPackageNotFoundError(f"Audit package {package_id} not found on application {application_id}.")

        manifest_data = json.loads(pkg.manifest_json)
        manifest = AuditPackageManifest.model_validate(manifest_data)
        read_model = AuditPackageRead.model_validate(pkg)
        return AuditPackageDetailRead(
            **read_model.model_dump(),
            manifest=manifest,
        )

    @classmethod
    def list_packages(
        cls,
        db: Session,
        *,
        application_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> AuditPackageListResponse:
        """List all audit packages generated for an application."""
        items, total = AuditPackageRepository.list_packages(db, application_id, skip=skip, limit=limit)
        return AuditPackageListResponse(
            items=[AuditPackageRead.model_validate(p) for p in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    @classmethod
    def get_package_download_bytes(
        cls,
        db: Session,
        *,
        application_id: int,
        package_id: int,
    ) -> tuple[bytes, str]:
        """Fetch package ZIP binary bytes for download."""
        pkg = AuditPackageRepository.get_by_id(db, application_id=application_id, package_id=package_id)
        if pkg is None or not pkg.storage_key:
            raise AuditPackageNotFoundError(f"Audit package {package_id} not found.")

        storage = get_storage_backend()
        if not storage.exists(pkg.storage_key):
            raise AuditPackageNotFoundError(f"Package storage file for {pkg.package_reference} is missing.")

        zip_bytes = storage.read(pkg.storage_key)
        filename = f"{pkg.package_name}.zip"
        return zip_bytes, filename

    @classmethod
    def verify_package_archive(
        cls,
        zip_bytes: bytes,
    ) -> AuditPackageVerificationResponse:
        """Perform comprehensive cryptographic tamper-evidence verification on an audit package archive."""
        tampered: list[str] = []
        missing: list[str] = []
        extra: list[str] = []

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf:
                archive_files = set(zf.namelist())

                if "manifest.json" not in archive_files:
                    return AuditPackageVerificationResponse(
                        verified=False,
                        computed_root_hash="",
                        expected_root_hash=None,
                        message="Invalid archive: missing manifest.json.",
                    )

                manifest_raw = zf.read("manifest.json").decode("utf-8")
                manifest_dict = json.loads(manifest_raw)
                manifest = AuditPackageManifest.model_validate(manifest_dict)

                # Recompute CHECKSUMS.txt from declared items
                recomputed_checksum_lines: list[str] = []

                for item in manifest.items:
                    if item.path not in archive_files:
                        missing.append(item.path)
                        continue

                    file_data = zf.read(item.path)
                    file_sha = hashlib.sha256(file_data).hexdigest()
                    if file_sha != item.sha256:
                        tampered.append(item.path)

                    recomputed_checksum_lines.append(f"{file_sha}  {item.path}")

                # Check for unexpected extra files
                declared_paths = {item.path for item in manifest.items} | {"manifest.json", "CHECKSUMS.txt"}
                for f in archive_files:
                    if f not in declared_paths:
                        extra.append(f)

                # Recompute root hash from canonical checksum lines
                recomputed_checksums = "\n".join(recomputed_checksum_lines) + "\n"
                computed_root = hashlib.sha256(recomputed_checksums.encode("utf-8")).hexdigest()

                is_valid = (
                    len(tampered) == 0
                    and len(missing) == 0
                    and len(extra) == 0
                    and computed_root == manifest.sha256_root_hash
                )

                if is_valid:
                    message = "Audit package passed cryptographic verification. All files and root digest are authentic."
                else:
                    message = "Integrity check failed: package contents differed from declared manifest."

                return AuditPackageVerificationResponse(
                    verified=is_valid,
                    package_reference=manifest.package_reference,
                    computed_root_hash=computed_root,
                    expected_root_hash=manifest.sha256_root_hash,
                    tampered_files=tampered,
                    missing_files=missing,
                    extra_files=extra,
                    message=message,
                )
        except Exception as exc:
            logger.error("Verification failed with exception: %s", exc)
            return AuditPackageVerificationResponse(
                verified=False,
                computed_root_hash="",
                expected_root_hash=None,
                message=f"Archive extraction failed: {exc}",
            )

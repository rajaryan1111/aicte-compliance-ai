"""Validation run, check results, and findings repository for database access."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Finding, ValidationCheckResult, ValidationRun


class ValidationRepository:
    """Encapsulates persistence operations for validation runs, check results, and findings."""

    @staticmethod
    def create_run(
        db: Session,
        *,
        application_id: int,
        evaluation_date: date,
        ruleset_version: str = "0.1.0-draft",
        status: str = "queued",
        triggered_by: str | None = None,
        outcome: str | None = None,
        consumed_version_ids: str | None = None,
        rule_snapshot: str | None = None,
        summary_counts: str | None = None,
        limitations: str | None = None,
    ) -> ValidationRun:
        """Create a new ValidationRun record for an application with provenance metadata."""
        run = ValidationRun(
            application_id=application_id,
            evaluation_date=evaluation_date,
            ruleset_version=ruleset_version,
            status=status,
            triggered_by=triggered_by,
            outcome=outcome,
            consumed_version_ids=consumed_version_ids,
            rule_snapshot=rule_snapshot,
            summary_counts=summary_counts,
            limitations=limitations,
        )
        db.add(run)
        return run

    @staticmethod
    def update_run(
        db: Session,
        run: ValidationRun,
        *,
        status: str | None = None,
        outcome: str | None = None,
        completed_at: datetime | None = None,
        consumed_version_ids: str | None = None,
        rule_snapshot: str | None = None,
        summary_counts: str | None = None,
        limitations: str | None = None,
    ) -> ValidationRun:
        """Update lifecycle status, outcome, and summary metadata on a validation run."""
        if status is not None:
            run.status = status
        if outcome is not None:
            run.outcome = outcome
        if completed_at is not None:
            run.completed_at = completed_at
        if consumed_version_ids is not None:
            run.consumed_version_ids = consumed_version_ids
        if rule_snapshot is not None:
            run.rule_snapshot = rule_snapshot
        if summary_counts is not None:
            run.summary_counts = summary_counts
        if limitations is not None:
            run.limitations = limitations
        db.flush()
        return run

    @staticmethod
    def get_run(db: Session, run_id: int) -> ValidationRun | None:
        """Retrieve a validation run by its primary key ID."""
        return db.get(ValidationRun, run_id)

    @staticmethod
    def list_runs_for_application(
        db: Session,
        application_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> list[ValidationRun]:
        """List validation runs for an application with pagination."""
        stmt = (
            select(ValidationRun)
            .where(ValidationRun.application_id == application_id)
            .order_by(ValidationRun.started_at.desc(), ValidationRun.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def create_check_result(
        db: Session,
        *,
        validation_run_id: int,
        check_id: str,
        check_name: str,
        category: str,
        status: str,
        document_version_id: int | None = None,
        message: str,
        evidence: str | None = None,
        limitations: str | None = None,
    ) -> ValidationCheckResult:
        """Create a deterministic check result record linked to a validation run."""
        result = ValidationCheckResult(
            validation_run_id=validation_run_id,
            check_id=check_id,
            check_name=check_name,
            category=category,
            status=status,
            document_version_id=document_version_id,
            message=message,
            evidence=evidence,
            limitations=limitations,
        )
        db.add(result)
        return result

    @staticmethod
    def list_check_results_for_run(
        db: Session,
        validation_run_id: int,
    ) -> list[ValidationCheckResult]:
        """List all deterministic check results for a validation run."""
        stmt = (
            select(ValidationCheckResult)
            .where(ValidationCheckResult.validation_run_id == validation_run_id)
            .order_by(ValidationCheckResult.id.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def create_finding(
        db: Session,
        *,
        validation_run_id: int,
        code: str,
        summary: str,
        severity: str = "warning",
        status: str = "open",
        document_version_id: int | None = None,
        requirement_assessment_id: int | None = None,
        confidence: float | None = None,
        evidence: str | None = None,
    ) -> Finding:
        """Create a Finding linked to a validation run and optional document version."""
        finding = Finding(
            validation_run_id=validation_run_id,
            document_version_id=document_version_id,
            requirement_assessment_id=requirement_assessment_id,
            confidence=confidence,
            code=code,
            summary=summary,
            severity=severity,
            status=status,
            evidence=evidence,
        )
        db.add(finding)
        return finding

    @staticmethod
    def list_findings_for_run(
        db: Session,
        validation_run_id: int,
    ) -> list[Finding]:
        """List all findings produced by a validation run."""
        stmt = (
            select(Finding)
            .where(Finding.validation_run_id == validation_run_id)
            .order_by(Finding.id.asc())
        )
        return list(db.scalars(stmt).all())

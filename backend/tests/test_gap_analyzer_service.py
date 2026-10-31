"""Regression tests for source-approved requirement registry behavior."""
from datetime import date
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models import Application, Institution, RuleApprovalRecord
from backend.app.services.gap_analyzer_service import active_requirement_records, get_requirements_for_application


def test_registry_does_not_expose_unverified_or_invalid_rule_definitions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        institution = Institution(institution_id="GAP-TEST-1", display_name="Gap Test")
        db.add(institution)
        db.flush()
        application = Application(institution_id=institution.id, application_type="eoa", academic_year="2025-2026", status="draft")
        db.add(application)
        db.flush()
        base = dict(
            rule_id="APH_TEST_RULE", rule_version=1, decision="approved", reviewer_id="director-1",
            reviewer_username="director", reviewer_role="regulatory_director", rationale="Reviewed source and interpretation.",
            source_title="Official test source", source_clause="1.1", source_page="1", source_document_version="2025",
            source_document_sha256="a" * 64, source_retrieved_at=date(2025, 1, 1), source_verified_by="verifier",
            source_verified_at=date(2025, 1, 2), source_verification_status="verified", statutory_interpretation_approved=True,
            effective_from=date(2025, 1, 1), effective_to=None, rule_definition_json=json.dumps({"not": "a valid rule definition"}),
        )
        db.add(RuleApprovalRecord(status="active", **base))
        db.add(RuleApprovalRecord(status="inactive", **{**base, "rule_id": "APH_INACTIVE_RULE"}))
        db.add(RuleApprovalRecord(status="active", **{**base, "rule_id": "APH_UNVERIFIED_RULE", "source_document_sha256": None}))
        db.flush()

        assert active_requirement_records(db) == []
        assert get_requirements_for_application(db, application) == []
    engine.dispose()

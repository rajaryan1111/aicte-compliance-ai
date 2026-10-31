"""API integration coverage for the deterministic Gap Analyzer lifecycle."""
from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timezone
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import ROLE_SUPER_ADMIN
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    Document,
    DocumentVersion,
    ExtractedField,
    Institution,
    InstitutionMembership,
    RuleApprovalRecord,
    User,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.services.rule_engine import build_aph_draft_rules


@pytest.fixture
def workflow_db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def workflow_client(workflow_db: Session, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-for-hs256-compliance!!")

    def override_db():
        yield workflow_db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_authenticated_gap_analysis_mapping_review_findings_and_history(
    workflow_client: TestClient, workflow_db: Session
):
    institution_a = Institution(institution_id="GAP-WORKFLOW-A", display_name="Workflow Institution A")
    institution_b = Institution(institution_id="GAP-WORKFLOW-B", display_name="Workflow Institution B")
    reviewer = User(username="gap_workflow_reviewer", hashed_password=get_password_hash("ValidPass123!"))
    foreign_user = User(username="gap_workflow_foreign", hashed_password=get_password_hash("ValidPass123!"))
    workflow_db.add_all([institution_a, institution_b, reviewer, foreign_user])
    workflow_db.flush()
    workflow_db.add_all([
        InstitutionMembership(user_id=reviewer.id, institution_id=institution_a.id, role=ROLE_SUPER_ADMIN, is_active=True),
        InstitutionMembership(user_id=foreign_user.id, institution_id=institution_b.id, role=ROLE_SUPER_ADMIN, is_active=True),
    ])
    application = Application(institution_id=institution_a.id, application_type="eoa", academic_year="2026-2027", status="submitted")
    foreign_application = Application(institution_id=institution_b.id, application_type="eoa", academic_year="2026-2027", status="submitted")
    workflow_db.add_all([application, foreign_application])
    workflow_db.flush()

    # Seed one well-formed, source-verified and approved deterministic rule version.
    draft = next(rule for rule in build_aph_draft_rules() if rule.rule_id == "APH_2024_FIRE_SAFETY")
    draft_data = draft.model_dump(mode="json")
    draft_data["source_provenance"].update({
        "status": "verified",
        "verified_by": "test-source-reviewer",
        "verified_at": date.today().isoformat(),
        "document_sha256": "a" * 64,
    })
    approval = RuleApprovalRecord(
        rule_id=draft.rule_id,
        rule_version=draft.version,
        status="active",
        decision="approved",
        reviewer_id=str(reviewer.id),
        reviewer_username=reviewer.username,
        reviewer_role=ROLE_SUPER_ADMIN,
        rationale="Test fixture records an approved source-backed rule version.",
        source_title=draft.source_title,
        source_clause=draft.source_clause,
        source_page=draft.source_page,
        source_document_version=draft.source_provenance.document_version,
        source_document_sha256="a" * 64,
        source_retrieved_at=draft.source_provenance.retrieved_at,
        source_verified_by="test-source-reviewer",
        source_verified_at=date.today(),
        source_verification_status="verified",
        statutory_interpretation_approved=True,
        decided_at=datetime.now(timezone.utc),
        effective_from=draft.effective_from,
        effective_to=draft.effective_to,
        rule_definition_json=json.dumps(draft_data),
    )
    workflow_db.add(approval)

    document = Document(application_id=application.id, document_type="fire_safety_certificate")
    workflow_db.add(document)
    workflow_db.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        storage_key="gap-workflow-fire.pdf",
        sha256="b" * 64,
        media_type="application/pdf",
        byte_size=128,
        scan_status="clean",
        processing_status="succeeded",
        uploaded_at=datetime.now(timezone.utc),
    )
    workflow_db.add(version)
    workflow_db.flush()
    document.current_version_id = version.id
    foreign_document = Document(application_id=foreign_application.id, document_type="fire_safety_certificate")
    workflow_db.add(foreign_document)
    workflow_db.flush()
    foreign_version = DocumentVersion(
        document_id=foreign_document.id,
        version_number=1,
        storage_key="foreign-gap-workflow-fire.pdf",
        sha256="c" * 64,
        media_type="application/pdf",
        byte_size=128,
        scan_status="clean",
        processing_status="succeeded",
        uploaded_at=datetime.now(timezone.utc),
    )
    workflow_db.add(foreign_version)
    workflow_db.flush()
    foreign_document.current_version_id = foreign_version.id
    field = ExtractedField(
        document_version_id=version.id,
        field_name="valid_until",
        raw_text="2026-01-01",
        normalized_value="2026-01-01",
        confidence=0.99,
        page_number=2,
        engine_name="integration-test",
    )
    workflow_db.add(field)
    workflow_db.commit()

    token = create_access_token(subject=reviewer.id, extra_claims={"username": reviewer.username})
    foreign_token = create_access_token(subject=foreign_user.id, extra_claims={"username": foreign_user.username})
    headers = {"Authorization": f"Bearer {token}"}
    foreign_headers = {"Authorization": f"Bearer {foreign_token}"}
    app_url = f"/api/v1/applications/{application.id}"

    requirements = workflow_client.get(f"{app_url}/gap-requirements", headers=headers)
    assert requirements.status_code == 200
    assert any(item["rule_id"] == draft.rule_id and item["version"] == draft.version for item in requirements.json())
    assert workflow_client.get(f"/api/v1/applications/{foreign_application.id}/gap-requirements", headers=headers).status_code == 404
    assert workflow_client.get(
        f"{app_url}/documents/{foreign_document.id}/versions/{foreign_version.id}/fields", headers=headers
    ).status_code == 404
    assert workflow_client.get(
        f"{app_url}/documents/{foreign_document.id}/versions/{foreign_version.id}/download", headers=headers
    ).status_code == 404

    mapping_response = workflow_client.post(
        f"{app_url}/requirement-evidence-mappings",
        headers=headers,
        json={
            "rule_approval_id": approval.id,
            "document_version_id": version.id,
            "extracted_field_id": field.id,
            "page_number": 2,
            "evidence_excerpt": "Fire certificate valid until 2026-01-01.",
            "rationale": "The certificate is mapped to the fire safety clause.",
        },
    )
    assert mapping_response.status_code == 201, mapping_response.text
    mapping_id = mapping_response.json()["id"]

    review_response = workflow_client.patch(
        f"{app_url}/requirement-evidence-mappings/{mapping_id}",
        headers=headers,
        json={"status": "confirmed", "sufficiency_status": "sufficient", "rationale": "Reviewer confirmed this source record."},
    )
    assert review_response.status_code == 200, review_response.text
    assert review_response.json()["review_history"][-1]["status"] == "confirmed"
    assert review_response.json()["review_history"][-1]["sufficiency_status"] == "sufficient"

    validation = workflow_client.post(f"{app_url}/validate", headers=headers, json={"checklist_type": "default"})
    assert validation.status_code == 201, validation.text
    run_id = validation.json()["validation_run"]["id"]
    analysis_response = workflow_client.get(f"{app_url}/gap-analysis?run_id={run_id}", headers=headers)
    assert analysis_response.status_code == 200, analysis_response.text
    analysis = analysis_response.json()
    fire_assessment = next(item for item in analysis["requirements"] if item["rule_id"] == draft.rule_id)
    assert fire_assessment["outcome_status"] == "potential_gap"
    assert fire_assessment["evidence"][0]["document_version_id"] == version.id
    assert fire_assessment["findings"]
    finding = fire_assessment["findings"][0]
    assert finding["evidence"][0]["document_version_id"] == version.id
    assert finding["evidence"][0]["page_number"] == 2

    # Refresh-like retrieval returns the persisted mapping decision and run snapshot.
    refreshed_mappings = workflow_client.get(f"{app_url}/requirement-evidence-mappings", headers=headers)
    assert refreshed_mappings.status_code == 200
    assert refreshed_mappings.json()[0]["review_history"] == review_response.json()["review_history"]
    old_snapshot = workflow_client.get(f"{app_url}/gap-analysis?run_id={run_id}", headers=headers)
    assert old_snapshot.json()["requirements"][0]["validation_run_id"] == run_id
    first_run_findings = workflow_client.get(f"{app_url}/validation-runs/{run_id}/findings", headers=headers)
    assert first_run_findings.status_code == 200
    first_findings = first_run_findings.json()
    assert len(first_findings) == 2  # Existing expiry check plus requirement-linked statutory finding.
    assert sum(item["code"] == f"REGULATORY_DEFICIENCY_{draft.rule_id}" for item in first_findings) == 1

    # A reassessment creates a distinct historical run and does not duplicate requirement findings within either run.
    second_validation = workflow_client.post(f"{app_url}/validate", headers=headers, json={"checklist_type": "default"})
    assert second_validation.status_code == 201, second_validation.text
    second_run_id = second_validation.json()["validation_run"]["id"]
    assert second_run_id != run_id
    second_findings = workflow_client.get(f"{app_url}/validation-runs/{second_run_id}/findings", headers=headers).json()
    assert sum(item["code"] == f"REGULATORY_DEFICIENCY_{draft.rule_id}" for item in second_findings) == 1
    runs = workflow_client.get(f"{app_url}/validation-runs?skip=0&limit=100", headers=headers)
    assert runs.status_code == 200
    assert {item["id"] for item in runs.json()["items"]} >= {run_id, second_run_id}
    assert workflow_client.get(f"{app_url}/gap-analysis?run_id={run_id}", headers=headers).json()["metrics"]["validation_run_id"] == run_id

    assert workflow_client.get(f"/api/v1/applications/{application.id}/gap-analysis?run_id={run_id}", headers=foreign_headers).status_code == 404
    assert workflow_client.get(f"{app_url}/gap-analysis?run_id={run_id}").status_code == 401

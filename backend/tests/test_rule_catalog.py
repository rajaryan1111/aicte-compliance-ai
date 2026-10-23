import pytest
from pydantic import ValidationError

from backend.app.rule_catalog import (
    ApprovalDecision,
    RuleLifecycle,
    RuleVersionDraft,
    SourceVerificationStatus,
)


def valid_rule_payload():
    """A synthetic rule payload. It is test data, not an AICTE requirement."""
    return {
        "rule_id": "TEST_DOCUMENT_RULE",
        "version": 1,
        "title": "Synthetic source-backed test rule",
        "description": "A synthetic rule used to test catalogue validation only.",
        "source_title": "Synthetic Regulatory Source for Tests",
        "source_issuer": "Synthetic Test Authority",
        "source_url": "https://example.org/test-source",
        "source_clause": "Section 1",
        "source_page": "1",
        "source_provenance": {
            "status": "verified",
            "document_version": "synthetic-source-v1",
            "retrieved_at": "2025-12-01",
            "verified_by": "synthetic-reviewer",
            "verified_at": "2025-12-02",
        },
        "effective_from": "2026-01-01",
        "applicability": {
            "application_types": ["eoa"],
            "academic_years": ["2026-27"],
            "conditions": ["Synthetic test condition applies."],
        },
        "interpretation": "This synthetic interpretation is not an AICTE requirement.",
        "limitations": ["Synthetic test only; not an official regulatory rule."],
        "reviewer_actions": ["Inspect the synthetic finding."],
        "test_cases": [
            {
                "name": "Positive synthetic case",
                "category": "positive",
                "expected_status": "passed",
                "notes": "Synthetic expected outcome.",
            },
            {
                "name": "Negative synthetic case",
                "category": "negative",
                "expected_status": "attention_required",
                "notes": "Synthetic expected outcome.",
            },
            {
                "name": "Boundary synthetic case",
                "category": "boundary",
                "expected_status": "human_review_required",
                "notes": "Synthetic expected outcome.",
            },
            {
                "name": "Exception synthetic case",
                "category": "exception",
                "expected_status": "not_applicable",
                "notes": "Synthetic expected outcome.",
            },
        ],
        "approval": {
            "reviewer_id": "synthetic-approver",
            "decision": "approved",
            "decided_at": "2025-12-03",
            "rationale": "Synthetic approval used only to test the gate.",
        },
    }


def test_rule_defaults_to_draft():
    rule = RuleVersionDraft.model_validate(valid_rule_payload())

    assert rule.lifecycle == RuleLifecycle.DRAFT
    assert rule.rule_id == "TEST_DOCUMENT_RULE"
    assert rule.source_provenance.status is SourceVerificationStatus.VERIFIED


def test_active_rule_requires_all_test_categories():
    payload = valid_rule_payload()
    payload["lifecycle"] = "active"
    payload["test_cases"] = payload["test_cases"][:2]

    with pytest.raises(ValidationError):
        RuleVersionDraft.model_validate(payload)


def test_active_rule_requires_effective_from():
    payload = valid_rule_payload()
    payload["lifecycle"] = "active"
    payload["effective_from"] = None

    with pytest.raises(ValidationError):
        RuleVersionDraft.model_validate(payload)


def test_effective_to_cannot_precede_effective_from():
    payload = valid_rule_payload()
    payload["effective_from"] = "2026-05-01"
    payload["effective_to"] = "2026-04-30"

    with pytest.raises(ValidationError):
        RuleVersionDraft.model_validate(payload)


def test_unknown_fields_are_rejected():
    payload = valid_rule_payload()
    payload["execute_python"] = "print('unsafe')"

    with pytest.raises(ValidationError):
        RuleVersionDraft.model_validate(payload)


def test_verified_source_requires_named_reviewer_and_date():
    payload = valid_rule_payload()
    payload["source_provenance"] = {
        "status": "verified",
        "document_version": "synthetic-source-v1",
        "retrieved_at": "2025-12-01",
    }

    with pytest.raises(ValidationError, match="verified_by"):
        RuleVersionDraft.model_validate(payload)


def test_unverified_source_cannot_carry_verification_identity():
    payload = valid_rule_payload()
    payload["source_provenance"]["status"] = "unverified"

    with pytest.raises(ValidationError, match="Verification details"):
        RuleVersionDraft.model_validate(payload)


def test_verification_cannot_precede_retrieval():
    payload = valid_rule_payload()
    payload["source_provenance"]["verified_at"] = "2025-11-01"

    with pytest.raises(ValidationError, match="verified_at"):
        RuleVersionDraft.model_validate(payload)


def test_active_rule_requires_verified_source():
    payload = valid_rule_payload()
    payload["lifecycle"] = "active"
    payload["source_provenance"] = {
        "status": "in_review",
        "document_version": "synthetic-source-v1",
        "retrieved_at": "2025-12-01",
    }

    with pytest.raises(ValidationError, match="verified source"):
        RuleVersionDraft.model_validate(payload)


def test_active_rule_requires_explicit_approval_record():
    payload = valid_rule_payload()
    payload["lifecycle"] = "active"
    del payload["approval"]

    with pytest.raises(ValidationError, match="approval record"):
        RuleVersionDraft.model_validate(payload)


def test_active_rule_rejects_rejected_approval_decision():
    payload = valid_rule_payload()
    payload["lifecycle"] = "active"
    payload["approval"]["decision"] = "rejected"

    with pytest.raises(ValidationError, match="approved decision"):
        RuleVersionDraft.model_validate(payload)


def test_approval_cannot_precede_verification_or_retrieval():
    payload = valid_rule_payload()
    payload["approval"]["decided_at"] = "2025-11-30"

    with pytest.raises(ValidationError, match="retrieval date"):
        RuleVersionDraft.model_validate(payload)

    payload = valid_rule_payload()
    payload["lifecycle"] = "active"
    payload["source_provenance"]["verified_at"] = "2025-12-10"
    payload["approval"]["decided_at"] = "2025-12-05"

    with pytest.raises(ValidationError, match="Approval must not precede"):
        RuleVersionDraft.model_validate(payload)


def test_approval_decision_enum_is_closed():
    payload = valid_rule_payload()
    payload["approval"]["decision"] = "maybe"

    with pytest.raises(ValidationError):
        RuleVersionDraft.model_validate(payload)

    assert ApprovalDecision.APPROVED.value == "approved"


# --- regression tests added by the 2026-10-23 foundation audit -------------


def test_active_rule_rejects_effective_date_before_source_publication():
    payload = valid_rule_payload()
    payload["lifecycle"] = "active"
    payload["publication_date"] = "2026-06-01"
    payload["effective_from"] = "2026-01-01"

    with pytest.raises(ValidationError, match="publication_date"):
        RuleVersionDraft.model_validate(payload)


def test_non_active_rule_may_record_publication_without_effective_date():
    payload = valid_rule_payload()
    payload["publication_date"] = "2026-06-01"
    payload["effective_from"] = None

    rule = RuleVersionDraft.model_validate(payload)

    assert rule.lifecycle is RuleLifecycle.DRAFT

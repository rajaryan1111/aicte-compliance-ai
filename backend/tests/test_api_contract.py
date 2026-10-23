"""Contract tests for the two implemented HTTP endpoints.

These pin the *external* shape of the API: exact keys, exact order, exact value
domains and the exact error envelope. They exist so a rename or an added field
cannot silently break a frontend, and so the response models in
`backend/app/main.py` cannot drift from what is actually emitted.

Contract: docs/development/API_CONTRACT.md, version 0.1.0-draft.
Capture-side proof that the JSON did not change lives in
`frontend/tools/verify_fixtures.py`, which replays fixtures captured *before*
these models were introduced.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.main import (
    Finding,
    HealthResponse,
    ValidationResponse,
    app,
)

client = TestClient(app)

# Field order is part of the contract: it is what a consumer sees in the payload.
VALIDATE_KEYS = [
    "institution_id",
    "application_type",
    "status",
    "validation_scope",
    "missing_documents",
    "expired_documents",
    "findings",
    "checked_at",
    "source",
    "notice",
]
HEALTH_KEYS = ["status", "service"]

BASE_REQUEST = {
    "institution_id": "SYNTH-INST-001",
    "application_type": "eoa",
    "required_documents": ["aicte_approval", "mandatory_disclosure"],
}


def validate(payload: dict) -> dict:
    response = client.post("/api/v1/validate", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_health_returns_the_documented_body():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert list(body) == HEALTH_KEYS
    assert body == {"status": "ok", "service": "aicte-compliance-assistant"}


def test_validate_returns_exactly_the_documented_keys_in_order():
    body = validate({**BASE_REQUEST, "submitted_documents": list(BASE_REQUEST["required_documents"])})
    assert list(body) == VALIDATE_KEYS


def test_scope_and_source_are_pinned():
    body = validate(BASE_REQUEST)
    # The endpoint evaluates only the caller's list. Losing this marker would let a
    # consumer mistake the result for an authoritative AICTE check.
    assert body["validation_scope"] == "caller_supplied_checklist_only"
    assert body["source"] == "synthetic_demo_input"
    assert "does not load an authoritative AICTE ruleset" in body["notice"]


def test_status_values_are_limited_to_the_two_documented_ones():
    passing = validate({**BASE_REQUEST, "submitted_documents": list(BASE_REQUEST["required_documents"])})
    failing = validate({**BASE_REQUEST, "submitted_documents": []})
    assert passing["status"] == "preliminary_checks_passed"
    assert failing["status"] == "attention_required"
    for body in (passing, failing):
        assert body["status"] in {"preliminary_checks_passed", "attention_required"}


def test_missing_document_finding_shape():
    body = validate({**BASE_REQUEST, "submitted_documents": ["aicte_approval"]})
    assert body["missing_documents"] == ["mandatory_disclosure"]
    assert body["expired_documents"] == []
    (finding,) = body["findings"]
    assert list(finding) == ["code", "document_type", "message", "evidence"]
    assert finding["code"] == "MISSING_DOCUMENT"
    assert finding["document_type"] == "mandatory_disclosure"
    assert finding["evidence"] == {
        "source": "submitted_document_list",
        "observed": "not_submitted",
    }


def test_expired_document_finding_shape():
    body = validate(
        {
            **BASE_REQUEST,
            "submitted_documents": list(BASE_REQUEST["required_documents"]),
            "expiry_dates": {"aicte_approval": "2020-01-01"},
        }
    )
    assert body["expired_documents"] == ["aicte_approval"]
    (finding,) = body["findings"]
    assert finding["code"] == "DOCUMENT_EXPIRED"
    assert set(finding["evidence"]) == {"source", "expiry_date", "evaluation_date"}
    assert finding["evidence"]["source"] == "synthetic_demo_input"
    assert finding["evidence"]["expiry_date"] == "2020-01-01"
    # The evaluation date is the server's UTC date, not the client's.
    assert finding["evidence"]["evaluation_date"] == (
        datetime.now(timezone.utc).date().isoformat()
    )


def test_checked_at_is_a_utc_timestamp():
    body = validate(BASE_REQUEST)
    parsed = datetime.fromisoformat(body["checked_at"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_extra_request_fields_are_ignored_not_echoed():
    body = validate({**BASE_REQUEST, "unexpected_field": "ignored"})
    assert "unexpected_field" not in body
    assert list(body) == VALIDATE_KEYS


def test_validation_error_envelope_contains_no_project_fields():
    response = client.post("/api/v1/validate", json={"institution_id": "x"})
    assert response.status_code == 422
    body = response.json()
    assert list(body) == ["detail"]
    assert isinstance(body["detail"], list) and body["detail"]
    for entry in body["detail"]:
        assert {"loc", "msg", "type"} <= set(entry)
        assert entry["type"] == "missing"
    assert {entry["loc"][-1] for entry in body["detail"]} == {
        "application_type",
        "required_documents",
    }


def test_semantic_validation_errors_use_the_same_envelope():
    response = client.post(
        "/api/v1/validate",
        json={
            "institution_id": "   ",
            "application_type": "eoa",
            "required_documents": ["aicte_approval", " aicte_approval "],
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert list(body) == ["detail"]
    by_field = {entry["loc"][-1]: entry for entry in body["detail"]}
    assert by_field["institution_id"]["type"] == "value_error"
    assert "must not be blank" in by_field["institution_id"]["msg"]
    # Duplicates are rejected after trimming, so " x " collides with "x".
    assert by_field["required_documents"]["type"] == "value_error"
    assert "must not contain duplicates" in by_field["required_documents"]["msg"]


@pytest.mark.parametrize(
    "application_type", ["eoa", "new_program", "intake_change"]
)
def test_all_application_types_round_trip(application_type):
    body = validate(
        {**BASE_REQUEST, "application_type": application_type, "submitted_documents": []}
    )
    assert body["application_type"] == application_type


def test_response_models_accept_their_own_payload_unchanged():
    body = validate(
        {
            **BASE_REQUEST,
            "submitted_documents": ["aicte_approval"],
            "expiry_dates": {"mandatory_disclosure": "2020-01-01"},
        }
    )
    # type_: strict round trip. If a model and the emitted body disagree, a consumer
    # generating a client from the schema would be wrong.
    assert ValidationResponse.model_validate(body).model_dump(mode="json") == body
    assert HealthResponse.model_validate(client.get("/health").json()).model_dump(
        mode="json"
    ) == {"status": "ok", "service": "aicte-compliance-assistant"}


def test_openapi_documents_both_response_models():
    schema = client.get("/openapi.json").json()
    validate_schema = schema["paths"]["/api/v1/validate"]["post"]["responses"]["200"]
    health_schema = schema["paths"]["/health"]["get"]["responses"]["200"]
    assert "ValidationResponse" in str(validate_schema)
    assert "HealthResponse" in str(health_schema)
    component = schema["components"]["schemas"]["ValidationResponse"]
    # A single-value Literal becomes `const` in the OpenAPI schema, not `enum`.
    assert component["properties"]["validation_scope"]["const"] == (
        "caller_supplied_checklist_only"
    )
    assert component["properties"]["status"]["enum"] == [
        "attention_required",
        "preliminary_checks_passed",
    ]
    finding = schema["components"]["schemas"]["Finding"]
    assert finding["properties"]["code"]["enum"] == [
        "MISSING_DOCUMENT",
        "DOCUMENT_EXPIRED",
    ]


def test_finding_model_rejects_an_unknown_code():
    with pytest.raises(ValueError):
        Finding(code="LOOKS_FINE", document_type="x", message="y", evidence={})

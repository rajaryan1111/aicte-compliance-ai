"""Automated tests for validation errors on POST /api/v1/validate.

Task B2 (STARTER_TASKS.md): Explicitly tests the FastAPI validation error
contract without altering the wire format or runtime behavior.

Covers each required rejection scenario:
1. institution_id contains only whitespace.
2. institution_id exceeds its maximum permitted length.
3. application_type contains an unsupported value.
4. required_documents is an empty list.
5. required_documents contains duplicate document names after whitespace normalization.
6. required_documents contains a blank or whitespace-only document name.
7. submitted_documents contains a blank or whitespace-only document name.
8. expiry_dates contains keys that become duplicates after whitespace normalization.
9. expiry_dates contains a malformed date string.
Plus a positive control test showing that a valid request succeeds (200 OK)
and does not return a 4xx response.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

VALID_PAYLOAD: dict[str, Any] = {
    "institution_id": "SYNTH-INST-001",
    "application_type": "eoa",
    "required_documents": ["undertaking", "accreditation_certificate"],
    "submitted_documents": ["undertaking"],
    "expiry_dates": {"undertaking": "2030-01-01"},
}

EXPECTED_RESPONSE_KEYS = [
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


def make_payload(**overrides: Any) -> dict[str, Any]:
    """Return a copy of VALID_PAYLOAD with specified overrides."""
    payload = dict(VALID_PAYLOAD)
    payload.update(overrides)
    return payload


def assert_validation_rejection(
    response,
    *,
    expected_type: str,
    expected_loc: list[str | int],
) -> dict[str, Any]:
    """Verify HTTP 422, exact ['detail'] top-level key, and expected error type and loc."""
    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    body = response.json()
    assert list(body) == ["detail"], f"Expected top-level keys to be ['detail'], got: {list(body)}"
    assert isinstance(body["detail"], list) and len(body["detail"]) > 0

    matching = [
        entry
        for entry in body["detail"]
        if entry.get("type") == expected_type and entry.get("loc") == expected_loc
    ]
    assert matching, (
        f"Expected detail entry with type={expected_type!r} and loc={expected_loc!r}. "
        f"Observed detail: {body['detail']}"
    )
    return body


# --- Positive Control Test ---


def test_positive_control_valid_request_succeeds():
    """Verify a valid request succeeds (200 OK) and does not return 4xx."""
    response = client.post("/api/v1/validate", json=VALID_PAYLOAD)
    assert not (400 <= response.status_code < 500), f"Expected non-4xx, got {response.status_code}"
    assert response.status_code == 200
    body = response.json()
    assert "detail" not in body
    assert list(body) == EXPECTED_RESPONSE_KEYS
    assert body["institution_id"] == VALID_PAYLOAD["institution_id"]
    assert body["application_type"] == VALID_PAYLOAD["application_type"]
    assert body["status"] in {"attention_required", "preliminary_checks_passed"}
    assert body["validation_scope"] == "caller_supplied_checklist_only"


# --- Scenario 1: institution_id contains only whitespace ---


def test_scenario_1_institution_id_whitespace_only_rejected():
    """Reject institution_id that contains only whitespace."""
    payload = make_payload(institution_id="   ")
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="value_error",
        expected_loc=["body", "institution_id"],
    )
    assert len(body["detail"]) == 1


# --- Scenario 2: institution_id exceeds maximum permitted length ---


def test_scenario_2_institution_id_exceeding_max_length_rejected():
    """Reject institution_id exceeding its maximum length (100 characters)."""
    payload = make_payload(institution_id="A" * 101)
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="string_too_long",
        expected_loc=["body", "institution_id"],
    )
    assert len(body["detail"]) == 1


# --- Scenario 3: application_type contains an unsupported value ---


@pytest.mark.parametrize("invalid_type", ["unsupported_type", "invalid_enum", "other", ""])
def test_scenario_3_application_type_unsupported_value_rejected(invalid_type: str):
    """Reject application_type when given values outside allowed literals."""
    payload = make_payload(application_type=invalid_type)
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="literal_error",
        expected_loc=["body", "application_type"],
    )
    assert len(body["detail"]) == 1


# --- Scenario 4: required_documents is an empty list ---


def test_scenario_4_required_documents_empty_list_rejected():
    """Reject request when required_documents list is empty (min_length=1)."""
    payload = make_payload(required_documents=[])
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="too_short",
        expected_loc=["body", "required_documents"],
    )
    assert len(body["detail"]) == 1


# --- Scenario 5: required_documents duplicate document names after normalization ---


def test_scenario_5_required_documents_duplicate_after_whitespace_normalization_rejected():
    """Reject required_documents containing duplicate names after whitespace trimming."""
    payload = make_payload(required_documents=["undertaking", " undertaking "])
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="value_error",
        expected_loc=["body", "required_documents"],
    )
    assert len(body["detail"]) == 1


# --- Scenario 6: required_documents contains a blank or whitespace-only name ---


def test_scenario_6_required_documents_blank_name_rejected():
    """Reject required_documents containing a blank or whitespace-only item."""
    payload = make_payload(required_documents=["undertaking", "   "])
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="value_error",
        expected_loc=["body", "required_documents"],
    )
    assert len(body["detail"]) == 1


# --- Scenario 7: submitted_documents contains a blank or whitespace-only name ---


def test_scenario_7_submitted_documents_blank_name_rejected():
    """Reject submitted_documents containing a blank or whitespace-only item."""
    payload = make_payload(submitted_documents=["   "])
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="value_error",
        expected_loc=["body", "submitted_documents"],
    )
    assert len(body["detail"]) == 1


# --- Scenario 8: expiry_dates contains duplicate keys after whitespace normalization ---


def test_scenario_8_expiry_dates_duplicate_keys_after_normalization_rejected():
    """Reject expiry_dates containing keys that collide after whitespace trimming."""
    payload = make_payload(
        expiry_dates={"undertaking": "2030-01-01", " undertaking ": "2030-01-01"}
    )
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="value_error",
        expected_loc=["body", "expiry_dates"],
    )
    assert len(body["detail"]) == 1


# --- Scenario 9: expiry_dates contains a malformed date ---


def test_scenario_9_expiry_dates_malformed_date_rejected():
    """Reject expiry_dates when given an invalid date string."""
    payload = make_payload(expiry_dates={"undertaking": "not-a-date"})
    response = client.post("/api/v1/validate", json=payload)
    body = assert_validation_rejection(
        response,
        expected_type="date_from_datetime_parsing",
        expected_loc=["body", "expiry_dates", "undertaking"],
    )
    assert len(body["detail"]) == 1

"""Verify that the frontend fixtures still describe the real API.

Run this before building UI against a fixture, and in CI so a backend change that
alters the response cannot silently invalidate the frontend.

    python frontend/tools/verify_fixtures.py

It checks, for every file in `frontend/fixtures/`:

1. **Replay** — the recorded request still produces the recorded status code and
   body (ignoring `checked_at`, which is a timestamp).
2. **Timestamp** — `checked_at`, when present, is a valid UTC ISO-8601 timestamp.
3. **Contract** — a 200 `/api/v1/validate` body contains exactly the documented
   top-level keys; a 422 body contains only `detail`.
4. **Honesty** — no fixture may claim a compliance verdict. Keys such as
   `compliant`, `approved`, `verdict`, `eligible` and `accuracy` are rejected, and
   any `status` value must be one the API actually defines.

Exit codes: 0 clean, 1 at least one problem, 2 fixtures directory missing/empty.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "frontend" / "fixtures"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app  # noqa: E402

# Contract version this checker understands. Update together with
# docs/development/API_CONTRACT.md; a mismatch is a contract change, not a bug fix.
CONTRACT_VERSION = "0.1.0-draft"

VALIDATE_TOP_LEVEL_KEYS = {
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
}
HEALTH_TOP_LEVEL_KEYS = {"status", "service"}
VALIDATE_STATUS_VALUES = {"preliminary_checks_passed", "attention_required"}
FINDING_CODES = {"MISSING_DOCUMENT", "DOCUMENT_EXPIRED"}
FINDING_KEYS = {"code", "document_type", "message", "evidence"}
ERROR_TOP_LEVEL_KEYS = {"detail"}

# Words that would turn a preliminary checklist result into a compliance claim.
FORBIDDEN_KEYS = {
    "compliant",
    "compliance",
    "approved",
    "approval",
    "verdict",
    "eligible",
    "eligibility",
    "certified",
    "accuracy",
    "confidence_score",
}


def _walk_keys(payload: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(key)
            keys |= _walk_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            keys |= _walk_keys(item)
    return keys


def _is_utc_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _compare(actual: Any, expected: Any, path: str, problems: list[str]) -> None:
    """Compare recorded and live payloads, treating checked_at as opaque."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            problems.append(f"{path}: expected an object, got {type(actual).__name__}")
            return
        for key in sorted(set(actual) - set(expected)):
            problems.append(f"{path}.{key}: present in the live response, absent from the fixture")
        for key in sorted(set(expected) - set(actual)):
            problems.append(f"{path}.{key}: in the fixture, missing from the live response")
        for key in sorted(set(expected) & set(actual)):
            if key == "checked_at":
                continue
            _compare(actual[key], expected[key], f"{path}.{key}", problems)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list):
            problems.append(f"{path}: expected a list, got {type(actual).__name__}")
            return
        if len(actual) != len(expected):
            problems.append(f"{path}: {len(actual)} item(s) live, {len(expected)} in the fixture")
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=False)):
            _compare(actual_item, expected_item, f"{path}[{index}]", problems)
        return
    if actual != expected:
        problems.append(f"{path}: live {actual!r} != fixture {expected!r}")


def check_fixture(client: TestClient, fixture: dict[str, Any]) -> list[str]:
    case_id = fixture.get("case_id", "<unnamed>")
    problems: list[str] = []

    endpoint = fixture.get("endpoint", "")
    method, _, path = endpoint.partition(" ")
    if not path:
        return [f"{case_id}: 'endpoint' must look like 'GET /health'"]

    if method == "GET":
        response = client.get(path)
    elif method == "POST":
        response = client.post(path, json=fixture.get("request"))
    else:
        return [f"{case_id}: unsupported method {method!r}"]

    if response.status_code != fixture.get("expected_status"):
        problems.append(
            f"{case_id}: live status {response.status_code} != "
            f"recorded {fixture.get('expected_status')}"
        )

    body = response.json()
    _compare(body, fixture.get("expected_response"), case_id, problems)

    live_keys = set(body)
    if response.status_code == 200 and path == "/api/v1/validate":
        unexpected = live_keys - VALIDATE_TOP_LEVEL_KEYS
        missing = VALIDATE_TOP_LEVEL_KEYS - live_keys
        if unexpected:
            problems.append(f"{case_id}: undocumented top-level key(s) {sorted(unexpected)}")
        if missing:
            problems.append(f"{case_id}: documented top-level key(s) missing {sorted(missing)}")
        if not _is_utc_timestamp(str(body.get("checked_at", ""))):
            problems.append(f"{case_id}: checked_at is not a UTC ISO-8601 timestamp")
        if body.get("status") not in VALIDATE_STATUS_VALUES:
            problems.append(f"{case_id}: unknown status value {body.get('status')!r}")
        if body.get("validation_scope") != "caller_supplied_checklist_only":
            problems.append(f"{case_id}: validation_scope no longer marks the scope")
        for finding in body.get("findings", []):
            if set(finding) != FINDING_KEYS:
                problems.append(f"{case_id}: finding keys {sorted(finding)} != {sorted(FINDING_KEYS)}")
            if finding.get("code") not in FINDING_CODES:
                problems.append(f"{case_id}: unknown finding code {finding.get('code')!r}")
    elif response.status_code == 200 and path == "/health":
        if live_keys != HEALTH_TOP_LEVEL_KEYS:
            problems.append(f"{case_id}: /health keys {sorted(live_keys)}")
    elif response.status_code == 422:
        if live_keys != ERROR_TOP_LEVEL_KEYS:
            problems.append(f"{case_id}: 422 body must contain only 'detail', got {sorted(live_keys)}")

    forbidden = {key for key in _walk_keys(body) if key.lower() in FORBIDDEN_KEYS}
    if forbidden:
        problems.append(f"{case_id}: fixture implies a compliance verdict via {sorted(forbidden)}")

    return problems


def main() -> int:
    if not FIXTURE_DIR.is_dir():
        print(f"error: no fixtures directory at {FIXTURE_DIR}", file=sys.stderr)
        return 2

    paths = sorted(FIXTURE_DIR.glob("*.json"))
    if not paths:
        print(f"error: no fixtures in {FIXTURE_DIR}", file=sys.stderr)
        return 2

    client = TestClient(app)
    problems: list[str] = []
    for path in paths:
        try:
            fixture = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            problems.append(f"{path.name}: invalid JSON ({error})")
            continue
        problems.extend(check_fixture(client, fixture))

    if problems:
        print(f"{len(problems)} problem(s) across {len(paths)} fixture(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nIf the API change is intended, re-capture with "
            "`python frontend/tools/capture_fixtures.py` and update "
            "docs/development/API_CONTRACT.md in the same PR.",
            file=sys.stderr,
        )
        return 1

    print(f"fixtures OK: {len(paths)} case(s) match the live API (contract {CONTRACT_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

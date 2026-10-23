"""Capture frontend fixtures from the running API.

Never hand-write a fixture: a hand-written response is a guess about the API, and
guesses are how a frontend invents fields that do not exist. This script calls the
application with synthetic input and stores exactly what comes back.

    python frontend/tools/capture_fixtures.py            # rewrite frontend/fixtures/*.json
    python frontend/tools/capture_fixtures.py --check     # fail if a fixture is stale

`checked_at` is the only non-deterministic field; it is replaced with the literal
``"<checked_at>"`` and `verify_fixtures.py` asserts it is still a well-formed UTC
timestamp on the live response.

Everything here is synthetic. No real institution, person or document is used.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "frontend" / "fixtures"
CHECKED_AT_PLACEHOLDER = "<checked_at>"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app  # noqa: E402  (import after sys.path setup)

VALIDATE = "/api/v1/validate"

_BASE_REQUEST: dict[str, Any] = {
    "institution_id": "SYNTH-INST-001",
    "application_type": "eoa",
    "required_documents": ["aicte_approval", "mandatory_disclosure"],
}

# case_id -> (notes, method, path, body or None)
CASES: dict[str, tuple[str, str, str, dict[str, Any] | None]] = {
    "health-ok": (
        "Liveness probe. No input, no side effects.",
        "GET",
        "/health",
        None,
    ),
    "validate-ok": (
        "All required documents supplied, no expiry dates given: the supplied lists agree.",
        "POST",
        VALIDATE,
        {**_BASE_REQUEST, "submitted_documents": ["aicte_approval", "mandatory_disclosure"]},
    ),
    "validate-missing": (
        "One required document not submitted: MISSING_DOCUMENT, attention_required.",
        "POST",
        VALIDATE,
        {**_BASE_REQUEST, "submitted_documents": ["aicte_approval"]},
    ),
    "validate-expired": (
        "All documents supplied but one expired: DOCUMENT_EXPIRED, attention_required.",
        "POST",
        VALIDATE,
        {
            **_BASE_REQUEST,
            "submitted_documents": ["aicte_approval", "mandatory_disclosure"],
            "expiry_dates": {"aicte_approval": "2020-01-01"},
        },
    ),
    "validate-missing-and-expired": (
        "Both problems at once: two findings, deterministic order (missing first).",
        "POST",
        VALIDATE,
        {
            "institution_id": "SYNTH-INST-002",
            "application_type": "new_program",
            "required_documents": ["aicte_approval", "mandatory_disclosure", "land_record"],
            "submitted_documents": ["land_record"],
            "expiry_dates": {"land_record": "2019-12-31"},
        },
    ),
    "validate-future-expiry": (
        "Expiry date supplied but in the future: no finding, no expired_documents "
        "entry. Fixtures stay deterministic by using 2099 rather than today's date.",
        "POST",
        VALIDATE,
        {
            **_BASE_REQUEST,
            "submitted_documents": ["aicte_approval", "mandatory_disclosure"],
            "expiry_dates": {"mandatory_disclosure": "2099-12-31"},
        },
    ),
    "validate-422-missing-fields": (
        "Framework validation error: required body fields absent. No project fields.",
        "POST",
        VALIDATE,
        {"institution_id": "SYNTH-INST-003"},
    ),
    "validate-422-empty-checklist": (
        "Framework validation error: required_documents must have at least one item.",
        "POST",
        VALIDATE,
        {**_BASE_REQUEST, "required_documents": [], "submitted_documents": []},
    ),
    "validate-422-duplicate-documents": (
        "Model validator rejects duplicate document names after trimming.",
        "POST",
        VALIDATE,
        {
            **_BASE_REQUEST,
            "required_documents": ["aicte_approval", " aicte_approval "],
            "submitted_documents": ["aicte_approval"],
        },
    ),
}


def _strip_checked_at(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: (CHECKED_AT_PLACEHOLDER if key == "checked_at" else _strip_checked_at(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_strip_checked_at(item) for item in payload]
    return payload


def build_fixture(client: TestClient, case_id: str) -> dict[str, Any]:
    notes, method, path, body = CASES[case_id]
    if method == "GET":
        response = client.get(path)
    else:
        response = client.post(path, json=body)
    payload = response.json()
    return {
        "case_id": case_id,
        "notes": notes,
        "endpoint": f"{method} {path}",
        "request": body,
        "expected_status": response.status_code,
        "expected_response": _strip_checked_at(payload),
    }


def render(fixture: dict[str, Any]) -> str:
    return json.dumps(fixture, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture API fixtures for the frontend")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if any fixture differs from the live API response",
    )
    args = parser.parse_args(argv)

    client = TestClient(app)
    stale: list[str] = []
    written: list[str] = []
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    for case_id in CASES:
        fixture = build_fixture(client, case_id)
        text = render(fixture)
        path = FIXTURE_DIR / f"{case_id}.json"
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        if args.check:
            stale.append(path.name)
            continue
        path.write_text(text, encoding="utf-8")
        written.append(path.name)

    if args.check:
        if stale:
            print(
                "stale fixture(s) — the API response changed:\n  "
                + "\n  ".join(stale)
                + "\nRe-run: python frontend/tools/capture_fixtures.py",
                file=sys.stderr,
            )
            return 1
        print(f"fixtures up to date: {len(CASES)} cases")
        return 0

    print(f"wrote {len(written)} fixture(s), {len(CASES) - len(written)} already current")
    for name in written:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

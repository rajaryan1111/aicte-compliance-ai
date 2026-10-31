"""Live probe against a locally running backend (manual verification only, not collected by pytest).

Synthetic data only. It reads the SQLite file the local server is using, seeds two throwaway
institutions and users, and exercises the authenticated plan API the way a browser would.

Usage:
    PROBE_BASE=http://127.0.0.1:8000 PROBE_DB=/tmp/aicte-e2e.db \
        python scripts/live_plan_probe.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE = os.environ.get("PROBE_BASE", "http://127.0.0.1:8000")
DB = os.environ.get("PROBE_DB", str(REPO_ROOT / "aicte_dev.db"))

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(' :: ' + detail) if detail else ''}")
    if not ok:
        failures.append(name)


def call(method: str, path: str, token: str | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed, dict(exc.headers)


def token_for(username: str, password: str) -> str | None:
    status, payload, _ = call("POST", "/api/v1/auth/token", body={"username": username, "password": password})
    if status != 200:
        print("token failure", username, status, payload)
        return None
    return payload["access_token"]


def ensure_user(username: str, password: str, institution_ref: str, role: str) -> None:
    """Create a second tenant, user and membership directly (synthetic test data only)."""
    sys.path.insert(0, str(REPO_ROOT))
    from backend.app.core.security import get_password_hash
    from backend.app.db.models import Institution, InstitutionMembership, User

    if not Path(DB).exists():
        raise SystemExit(f"PROBE_DB does not exist: {DB}")
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("select id from institutions where institution_id = ?", (institution_ref,))
    row = cur.fetchone()
    if row:
        inst_id = row[0]
    else:
        cur.execute(
            "insert into institutions (institution_id, display_name, status, created_at) "
            "values (?, ?, 'active', datetime('now'))",
            (institution_ref, f"Synthetic {institution_ref}"),
        )
        inst_id = cur.lastrowid
    cur.execute("select id from users where username = ?", (username,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
    else:
        cur.execute(
            "insert into users (username, hashed_password, display_name, is_active, created_at, updated_at) "
            "values (?, ?, ?, 1, datetime('now'), datetime('now'))",
            (username, get_password_hash(password), f"Synthetic {username}"),
        )
        user_id = cur.lastrowid
    cur.execute(
        "select id from institution_memberships where user_id = ? and institution_id = ?",
        (user_id, inst_id),
    )
    if cur.fetchone():
        cur.execute(
            "update institution_memberships set role = ?, is_active = 1 where user_id = ? and institution_id = ?",
            (role, user_id, inst_id),
        )
    else:
        cur.execute(
            "insert into institution_memberships (user_id, institution_id, role, is_active, created_at) "
            "values (?, ?, ?, 1, datetime('now'))",
            (user_id, inst_id, role),
        )
    con.commit()
    con.close()
    del User, Institution, InstitutionMembership


def plan_body(institution_ref: str, plan_key: str, tasks: list[dict], policy: dict | None = None) -> dict:
    return {
        "institution_ref": institution_ref,
        "plan_key": plan_key,
        "application_type": "ECE_UG",
        "deadline_policy": policy or {"p1_days": 3, "p2_days": 7, "p3_buffer_days": 14, "p3_max_days": 21, "expiring_window_days": 60},
        "items": tasks,
    }


def task(key: str, due_offset: int, finding: str = "MISSING_DOCUMENT", priority: str = "P1") -> dict:
    return {
        "task_key": key,
        "document_id": f"doc-{key}",
        "document_label": f"Synthetic document {key}",
        "finding_code": finding,
        "priority": priority,
        "owner_role": "Registrar",
        "due_date": (date.today() + timedelta(days=due_offset)).isoformat(),
        "evidence_required": "Signed copy uploaded by the institution (synthetic).",
        "clause": "Appendix 4",
    }


def main() -> int:
    main_ref = "DEMO-INST-001"
    other_ref = "SYNTH-INST-002"

    # --- authentication required ---
    status, payload, _ = call("GET", f"/api/v1/institutions/{main_ref}/remediation-plans")
    check("unauthenticated list is rejected", status == 401, f"status={status}")
    status, _, _ = call("POST", f"/api/v1/institutions/{main_ref}/remediation-plans", body=plan_body(main_ref, "probe-noauth", [task("t1", 3)]))
    check("unauthenticated create is rejected", status == 401, f"status={status}")

    admin = token_for("admin", "admin123456")
    reviewer = token_for("reviewer", "reviewer123456")
    if not admin or not reviewer:
        return 1

    ensure_user("auditor1", "auditor123456", main_ref, "auditor")
    ensure_user("foreign_admin", "foreign123456", other_ref, "institution_admin")
    auditor = token_for("auditor1", "auditor123456")
    foreign = token_for("foreign_admin", "foreign123456")
    if not auditor or not foreign:
        return 1

    # --- create is idempotent ---
    plan_key = f"probe-{uuid4().hex[:8]}"
    body = plan_body(main_ref, plan_key, [task("t1", 3), task("t2", 9, "DOCUMENT_EXPIRED", "P2")])
    status, created, _ = call("POST", f"/api/v1/institutions/{main_ref}/remediation-plans", admin, body)
    check("create returns 201", status == 201, f"status={status} {created if status != 201 else ''}")
    plan_id = created["id"] if status == 201 else None

    status, again, _ = call("POST", f"/api/v1/institutions/{main_ref}/remediation-plans", admin, body)
    check("re-post is idempotent 200", status == 200 and again["id"] == plan_id, f"status={status}")

    # --- progress update + audit ---
    version = created["tasks"][0]["version"]
    status, updated, _ = call(
        "PATCH",
        f"/api/v1/institutions/{main_ref}/remediation-plans/{plan_id}/tasks/t1",
        admin,
        {"status": "done", "note": "SAR uploaded (synthetic).", "version": version},
    )
    check("task status update accepted", status == 200 and updated["status"] == "done", f"status={status}")
    check("version incremented", status == 200 and updated["version"] == version + 1, f"v={updated.get('version') if status == 200 else '?'}")
    check("actor attributed", status == 200 and updated["status_changed_by"] == "admin", f"by={updated.get('status_changed_by') if status == 200 else '?'}")

    status, conflict, headers = call(
        "PATCH",
        f"/api/v1/institutions/{main_ref}/remediation-plans/{plan_id}/tasks/t1",
        admin,
        {"status": "open", "version": version},
    )
    check("stale version rejected with 409", status == 409, f"status={status}")
    lower_headers = {k.lower(): v for k, v in headers.items()}
    check("409 carries current version header", lower_headers.get("x-current-version") == str(version + 1), f"hdr={lower_headers.get('x-current-version')}")

    # idempotent re-post must not reset progress
    status, again2, _ = call("POST", f"/api/v1/institutions/{main_ref}/remediation-plans", admin, body)
    statuses = {t["task_key"]: t["status"] for t in again2["tasks"]}
    check("idempotent re-post preserves progress", statuses.get("t1") == "done", f"statuses={statuses}")

    # --- RBAC ---
    status, _, _ = call(
        "PATCH",
        f"/api/v1/institutions/{main_ref}/remediation-plans/{plan_id}/tasks/t2",
        auditor,
        {"status": "in_progress", "version": 1},
    )
    check("read-only role cannot write (403)", status == 403, f"status={status}")
    status, _, _ = call("GET", f"/api/v1/institutions/{main_ref}/remediation-plans", auditor)
    check("read-only role can read", status == 200, f"status={status}")
    status, _, _ = call("GET", f"/api/v1/institutions/{main_ref}/remediation-plans")
    check("read requires auth", status == 401, f"status={status}")

    # --- tenant isolation ---
    status, _, _ = call("GET", f"/api/v1/institutions/{other_ref}/remediation-plans", admin)
    check("foreign institution list is concealed (404)", status == 404, f"status={status}")
    status, _, _ = call(
        "PATCH",
        f"/api/v1/institutions/{other_ref}/remediation-plans/{plan_id}/tasks/t2",
        admin,
        {"status": "done", "version": 1},
    )
    check("foreign institution write is concealed (404)", status == 404, f"status={status}")

    # --- validation ---
    bad = plan_body(main_ref, f"bad-{uuid4().hex[:8]}", [task("t1", 3)], {"p1_days": 10, "p2_days": 5})
    status, _, _ = call("POST", f"/api/v1/institutions/{main_ref}/remediation-plans", admin, bad)
    check("inconsistent deadline policy rejected (422)", status == 422, f"status={status}")
    dup = plan_body(main_ref, f"dup-{uuid4().hex[:8]}", [task("t1", 3), task("t1", 5)])
    status, _, _ = call("POST", f"/api/v1/institutions/{main_ref}/remediation-plans", admin, dup)
    check("duplicate task keys rejected (422)", status == 422, f"status={status}")
    mismatch = plan_body(main_ref, f"mis-{uuid4().hex[:8]}", [task("t1", 3)])
    mismatch["institution_ref"] = other_ref
    status, _, _ = call("POST", f"/api/v1/institutions/{main_ref}/remediation-plans", admin, mismatch)
    check("body/path institution mismatch rejected (422)", status == 422, f"status={status}")

    # --- audit trail ---
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute(
        "select action, actor_id, details from audit_events where target_type like '%remediation%' order by id desc limit 5"
    )
    rows = cur.fetchall()
    con.close()
    check("audit rows recorded for plan activity", len(rows) > 0, f"rows={rows[:2]}")

    print()
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

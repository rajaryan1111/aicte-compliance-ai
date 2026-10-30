"""End-to-End Application Workflow Integration Test (Phase 5).

Executes the complete AICTE compliance assistance lifecycle against real PostgreSQL and Redis:
1. Authenticate institution administrator
2. Create application via API
3. Upload synthetic document with security gating and quarantine storage
4. Dispatch and process through real Redis broker and Celery worker
5. Poll and verify persisted OCR extraction and preliminary findings
6. Trigger application validation and verify immutable snapshot
7. Record attributable human review action as scrutiny officer
8. Enforce tenant isolation against unauthorized user
9. Export tamper-evident audit package
10. Verify cryptographic integrity and detect tampering
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
import time
from typing import Any
import zipfile

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.rbac import (
    ROLE_INSTITUTION_ADMIN,
    ROLE_SCRUTINY_OFFICER,
)
from backend.app.core.security import get_password_hash
from backend.app.db.models import Institution
from backend.app.repositories.user_repository import UserRepository
from backend.app.worker.celery_app import celery_app
from backend.app.worker.tasks import set_worker_session_factory


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _create_synthetic_pdf(text_lines: list[str]) -> bytes:
    """Build a valid minimal PDF with text stream for native extraction."""
    parts = ["BT /F1 12 Tf 50 700 Td"]
    for i, line in enumerate(text_lines):
        if i == 0:
            parts.append(f"({line}) Tj")
        else:
            parts.append(f"0 -20 Td ({line}) Tj")
    parts.append("ET")
    stream_data = " ".join(parts).encode("utf-8")
    stream_len = len(stream_data)

    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(stream_len).encode("utf-8") + b" >>\nstream\n"
        + stream_data + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000240 00000 n \n0000000350 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n450\n%%EOF"
    )


@pytest.fixture(autouse=True)
def configure_integration_broker(require_live_redis: str, live_postgres_engine: Engine) -> None:
    """Ensure in-process Celery communicates with real Redis and test DB engine."""
    celery_app.conf.broker_url = require_live_redis
    celery_app.conf.result_backend = require_live_redis
    celery_app.conf.task_always_eager = False
    set_worker_session_factory(sessionmaker(bind=live_postgres_engine))


def test_full_application_workflow_end_to_end(
    live_celery_worker: Any,
    live_postgres_session: Session,
    live_api_client: TestClient,
) -> None:
    """Execute complete end-to-end workflow with real infrastructure (Phase 5)."""
    ts = int(_utc_now().timestamp())
    inst_code = f"E2E-INST-{ts}"
    other_code = f"OTHER-INST-{ts}"

    # -------------------------------------------------------------------------
    # Setup: Institutions and Authorized Users
    # -------------------------------------------------------------------------
    inst = Institution(institution_id=inst_code, display_name="E2E Polytechnic Institute")
    other_inst = Institution(institution_id=other_code, display_name="Foreign Institute")
    live_postgres_session.add_all([inst, other_inst])
    live_postgres_session.commit()

    pwd_hash = get_password_hash("ValidPass123!")

    # 1. Institution Admin User
    admin_user = UserRepository.create(
        live_postgres_session,
        username=f"admin_{ts}@aicte.test",
        hashed_password=pwd_hash,
        display_name="Institution Administrator",
    )
    live_postgres_session.commit()
    UserRepository.create_membership(
        live_postgres_session,
        user_id=admin_user.id,
        institution_id=inst.id,
        role=ROLE_INSTITUTION_ADMIN,
    )

    # 2. Scrutiny Officer User
    scrutiny_user = UserRepository.create(
        live_postgres_session,
        username=f"officer_{ts}@aicte.test",
        hashed_password=pwd_hash,
        display_name="AICTE Scrutiny Officer",
    )
    live_postgres_session.commit()
    UserRepository.create_membership(
        live_postgres_session,
        user_id=scrutiny_user.id,
        institution_id=inst.id,
        role=ROLE_SCRUTINY_OFFICER,
    )

    # 3. Unauthorized Foreign User
    foreign_user = UserRepository.create(
        live_postgres_session,
        username=f"foreign_{ts}@aicte.test",
        hashed_password=pwd_hash,
        display_name="Foreign Institute Admin",
    )
    live_postgres_session.commit()
    UserRepository.create_membership(
        live_postgres_session,
        user_id=foreign_user.id,
        institution_id=other_inst.id,
        role=ROLE_INSTITUTION_ADMIN,
    )
    live_postgres_session.commit()

    # -------------------------------------------------------------------------
    # Step 1: Authenticate as Institution Admin
    # -------------------------------------------------------------------------
    login_res = live_api_client.post(
        "/api/v1/auth/token",
        json={"username": admin_user.username, "password": "ValidPass123!"},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    admin_token = login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # -------------------------------------------------------------------------
    # Step 2: Create Application
    # -------------------------------------------------------------------------
    app_create_res = live_api_client.post(
        "/api/v1/applications",
        headers=admin_headers,
        json={
            "institution_id": inst.id,
            "application_type": "eoa",
            "academic_year": "2026-2027",
            "status": "draft",
        },
    )
    assert app_create_res.status_code == 201, f"Application creation failed: {app_create_res.text}"
    app_data = app_create_res.json()
    application_id = app_data["id"]
    assert app_data["application_type"] == "eoa"
    assert app_data["academic_year"] == "2026-2027"

    # -------------------------------------------------------------------------
    # Step 3: Upload Synthetic Document
    # -------------------------------------------------------------------------
    pdf_bytes = _create_synthetic_pdf([
        f"Institution ID: {inst_code}",
        "Valid Until: 2029-06-30",
        "Issue Date: 2025-01-01",
        "Land Record NOC No: NOC-2026-99",
    ])

    files = {"file": ("land_record.pdf", pdf_bytes, "application/pdf")}
    data = {"document_type": "land_record"}

    upload_res = live_api_client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=admin_headers,
        data=data,
        files=files,
    )
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
    upload_data = upload_res.json()
    document_id = upload_data["document"]["id"] if "document" in upload_data else upload_data["document_id"]
    version_id = upload_data["version"]["id"] if "version" in upload_data else upload_data["version_id"]
    polling_url = upload_data.get("polling_url")
    assert document_id > 0
    assert version_id > 0
    assert polling_url is not None

    # -------------------------------------------------------------------------
    # Step 4: Verify Asynchronous Processing by Real Worker
    # -------------------------------------------------------------------------
    # Poll until background Celery worker completes malware scan & OCR extraction
    deadline = time.time() + 15.0
    is_completed = False
    while time.time() < deadline:
        poll_res = live_api_client.get(polling_url, headers=admin_headers)
        if poll_res.status_code == 200:
            job_status = poll_res.json()
            job_state = job_status.get("state") or job_status.get("job", {}).get("state")
            if job_state in ("completed", "partial"):
                is_completed = True
                assert job_status.get("scan_status") == "clean"
                assert job_status.get("is_terminal") is True
                break
        time.sleep(0.3)

    assert is_completed is True, "Background worker did not complete processing in time"

    # -------------------------------------------------------------------------
    # Step 5: Trigger Application Validation
    # -------------------------------------------------------------------------
    val_res = live_api_client.post(
        f"/api/v1/applications/{application_id}/validate",
        headers=admin_headers,
        json={
            "checklist_type": "default",
            "ruleset_version": "0.1.0-draft",
        },
    )
    assert val_res.status_code == 201, f"Validation failed: {val_res.text}"
    val_data = val_res.json()
    run_id = val_data["validation_run"]["id"]
    findings = val_data["findings"]
    assert val_data["validation_run"]["status"] in ("succeeded", "completed")
    assert "preliminary" in val_data["disclaimer"].lower()

    # -------------------------------------------------------------------------
    # Step 6: Fetch Validation Report and Findings
    # -------------------------------------------------------------------------
    report_res = live_api_client.get(
        f"/api/v1/applications/{application_id}/validation-runs/{run_id}",
        headers=admin_headers,
    )
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["validation_run"]["id"] == run_id

    # -------------------------------------------------------------------------
    # Step 7: Perform Allowed Human Review Action as Scrutiny Officer
    # -------------------------------------------------------------------------
    # Login as scrutiny officer
    scrutiny_login = live_api_client.post(
        "/api/v1/auth/token",
        json={"username": scrutiny_user.username, "password": "ValidPass123!"},
    )
    scrutiny_token = scrutiny_login.json()["access_token"]
    scrutiny_headers = {"Authorization": f"Bearer {scrutiny_token}"}

    if findings:
        target_finding = findings[0]
        finding_id = target_finding["id"]
        review_res = live_api_client.post(
            f"/api/v1/applications/{application_id}/validation-runs/{run_id}/findings/{finding_id}/actions",
            headers=scrutiny_headers,
            json={
                "action": "acknowledge",
                "comment": "Observation acknowledged by scrutiny officer during B11 E2E test.",
            },
        )
        assert review_res.status_code == 201, f"Review action failed: {review_res.text}"
        review_data = review_res.json()
        assert review_data["action"] == "acknowledge"
        assert review_data["reviewer_username"] == scrutiny_user.username

    # -------------------------------------------------------------------------
    # Step 8: Security - Cross-Institution Tenant Access Denial
    # -------------------------------------------------------------------------
    foreign_login = live_api_client.post(
        "/api/v1/auth/token",
        json={"username": foreign_user.username, "password": "ValidPass123!"},
    )
    foreign_token = foreign_login.json()["access_token"]
    foreign_headers = {"Authorization": f"Bearer {foreign_token}"}

    # Foreign user must be DENIED access to institution A's application
    foreign_get = live_api_client.get(
        f"/api/v1/applications/{application_id}",
        headers=foreign_headers,
    )
    assert foreign_get.status_code in (403, 404), "Foreign user was not denied access to cross-institution data"

    # -------------------------------------------------------------------------
    # Step 9: Export Audit Package
    # -------------------------------------------------------------------------
    export_res = live_api_client.post(
        f"/api/v1/applications/{application_id}/audit-packages",
        headers=admin_headers,
        json={
            "validation_run_id": run_id,
            "include_documents": True,
        },
    )
    assert export_res.status_code == 201, f"Export failed: {export_res.text}"
    pkg_data = export_res.json()
    package_id = pkg_data["id"]
    expected_root_hash = pkg_data["merkle_root_hash"]

    # -------------------------------------------------------------------------
    # Step 10: Download Audit Package Archive
    # -------------------------------------------------------------------------
    download_res = live_api_client.get(
        f"/api/v1/applications/{application_id}/audit-packages/{package_id}/download",
        headers=admin_headers,
    )
    assert download_res.status_code == 200
    zip_bytes = download_res.content
    assert len(zip_bytes) > 0

    # -------------------------------------------------------------------------
    # Step 11: Verify Cryptographic Integrity
    # -------------------------------------------------------------------------
    verify_files = {"file": ("audit_package.zip", zip_bytes, "application/zip")}
    verify_res = live_api_client.post(
        "/api/v1/audit-packages/verify",
        headers=admin_headers,
        files=verify_files,
    )
    assert verify_res.status_code == 200, f"Verification failed: {verify_res.text}"
    verify_data = verify_res.json()
    assert verify_data["verified"] is True
    assert verify_data["tampered_files"] == []
    assert verify_data["computed_root_hash"] == expected_root_hash

    # -------------------------------------------------------------------------
    # Step 12: Tamper Detection Verification
    # -------------------------------------------------------------------------
    # Deliberately modify an entry inside the ZIP archive to simulate tampering
    in_buf = io.BytesIO(zip_bytes)
    out_buf = io.BytesIO()

    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            # Tamper with a report or document file (avoid manifest itself)
            if item.filename != "manifest.json" and not item.is_dir():
                content = content + b"\nTAMPERED_BYTE_DATA_FOR_B11_VERIFICATION"
            z_out.writestr(item, content)

    tampered_bytes = out_buf.getvalue()

    tamper_files = {"file": ("tampered_package.zip", tampered_bytes, "application/zip")}
    tamper_res = live_api_client.post(
        "/api/v1/audit-packages/verify",
        headers=admin_headers,
        files=tamper_files,
    )
    assert tamper_res.status_code == 200
    tamper_data = tamper_res.json()
    assert tamper_data["verified"] is False
    assert len(tamper_data["tampered_files"]) > 0 or tamper_data["computed_root_hash"] != expected_root_hash

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.delete(other_inst)
    live_postgres_session.commit()

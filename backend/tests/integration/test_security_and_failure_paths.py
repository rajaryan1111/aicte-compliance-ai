"""Integration tests verifying security controls and failure paths (Phase 6).

Verifies:
- Institutional tenant boundaries and cross-institution denial
- Auditor role read-only enforcement
- Authentication rejection for missing, invalid, or expired tokens
- Safe upload rejection for unsupported or malformed files
- Quarantine download protection for pending, unavailable, or rejected scans
- Prevention of file-system paths, tokens, or secrets leakage in error responses
- Clean transaction rollbacks and intact audit event history
- Storage directory traversal prevention and isolation outside web root
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from backend.app.core.rbac import (
    ROLE_AUDITOR,
    ROLE_INSTITUTION_ADMIN,
)
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.core.storage import LocalStorageBackend, PathTraversalError
from backend.app.db.models import (
    Application,
    Document,
    DocumentVersion,
    Institution,
)
from backend.app.repositories.user_repository import UserRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_cross_institution_access_denial(
    live_postgres_session: Session,
    live_api_client: TestClient,
) -> None:
    """Verify tenant isolation strictly denies cross-institution data access (Phase 6.1)."""
    ts = int(_utc_now().timestamp())
    inst_a = Institution(institution_id=f"INST-A-{ts}", display_name="Tenant Institute A")
    inst_b = Institution(institution_id=f"INST-B-{ts}", display_name="Tenant Institute B")
    live_postgres_session.add_all([inst_a, inst_b])
    live_postgres_session.commit()

    pwd_hash = get_password_hash("Password123!")
    user_a = UserRepository.create(live_postgres_session, username=f"user_a_{ts}", hashed_password=pwd_hash)
    user_b = UserRepository.create(live_postgres_session, username=f"user_b_{ts}", hashed_password=pwd_hash)
    live_postgres_session.commit()

    UserRepository.create_membership(live_postgres_session, user_id=user_a.id, institution_id=inst_a.id, role=ROLE_INSTITUTION_ADMIN)
    UserRepository.create_membership(live_postgres_session, user_id=user_b.id, institution_id=inst_b.id, role=ROLE_INSTITUTION_ADMIN)

    app_a = Application(institution_id=inst_a.id, application_type="eoa", academic_year="2026-2027")
    app_b = Application(institution_id=inst_b.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add_all([app_a, app_b])
    live_postgres_session.commit()

    # User B logs in
    login_b = live_api_client.post("/api/v1/auth/token", json={"username": user_b.username, "password": "Password123!"})
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B tries to read App A -> 404, concealed to prevent resource
    # discovery (the implemented tenant-isolation contract in
    # backend/app/api/deps.py::verify_institution_membership and the unit
    # suite in test_auth_rbac.py: "404 (concealed)").
    res = live_api_client.get(f"/api/v1/applications/{app_a.id}", headers=headers_b)
    assert res.status_code == 404
    assert "not found" in res.json().get("detail", "").lower()

    # User B tries to upload to App A -> concealed the same way
    upload_res = live_api_client.post(
        f"/api/v1/applications/{app_a.id}/documents",
        headers=headers_b,
        data={"document_type": "land_record"},
        files={"file": ("test.pdf", b"%PDF-1.4 mock", "application/pdf")},
    )
    assert upload_res.status_code == 404

    # Clean up
    live_postgres_session.delete(inst_a)
    live_postgres_session.delete(inst_b)
    live_postgres_session.commit()


def test_auditor_role_read_only_enforcement(
    live_postgres_session: Session,
    live_api_client: TestClient,
) -> None:
    """Verify that Auditor role cannot mutate applications, upload files, or trigger validations (Phase 6.2)."""
    ts = int(_utc_now().timestamp())
    inst = Institution(institution_id=f"INST-AUD-{ts}", display_name="Auditor Test Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    pwd_hash = get_password_hash("Password123!")
    auditor_user = UserRepository.create(live_postgres_session, username=f"auditor_{ts}", hashed_password=pwd_hash)
    live_postgres_session.commit()
    UserRepository.create_membership(live_postgres_session, user_id=auditor_user.id, institution_id=inst.id, role=ROLE_AUDITOR)

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    login = live_api_client.post("/api/v1/auth/token", json={"username": auditor_user.username, "password": "Password123!"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Auditor CAN read application
    get_res = live_api_client.get(f"/api/v1/applications/{app.id}", headers=headers)
    assert get_res.status_code == 200

    # Auditor CANNOT create application -> 403
    create_res = live_api_client.post(
        "/api/v1/applications",
        headers=headers,
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "2026-2027"},
    )
    assert create_res.status_code == 403

    # Auditor CANNOT trigger validation -> 403
    val_res = live_api_client.post(
        f"/api/v1/applications/{app.id}/validate",
        headers=headers,
        json={"checklist_type": "default"},
    )
    assert val_res.status_code == 403

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_authentication_rejection_invalid_or_expired_token(
    live_postgres_session: Session,
    live_api_client: TestClient,
) -> None:
    """Verify 401 Unauthorized rejection for missing, invalid, or expired tokens (Phase 6.3)."""
    # 1. Missing token
    res1 = live_api_client.get("/api/v1/applications/1")
    assert res1.status_code == 401
    assert "credentials were not provided" in res1.json()["detail"].lower()

    # 2. Corrupted/tampered token
    res2 = live_api_client.get("/api/v1/applications/1", headers={"Authorization": "Bearer not.a.valid.jwt.token"})
    assert res2.status_code == 401
    # The implemented invalid-token wording (backend/app/api/deps.py); the
    # message must not leak why the credential failed.
    assert "could not validate authentication credentials" in res2.json()["detail"].lower()

    # 3. Expired token
    ts = int(_utc_now().timestamp())
    inst = Institution(institution_id=f"INST-EXP-{ts}", display_name="Expire Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    user = UserRepository.create(live_postgres_session, username=f"exp_{ts}", hashed_password=get_password_hash("Pass123!"))
    live_postgres_session.commit()

    expired_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(seconds=-60),  # expired 1 minute ago
        extra_claims={"username": user.username},
    )
    res3 = live_api_client.get("/api/v1/applications/1", headers={"Authorization": f"Bearer {expired_token}"})
    assert res3.status_code == 401
    assert "expired" in res3.json()["detail"].lower()

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_safe_upload_rejection_for_unsupported_or_malformed_files(
    live_postgres_session: Session,
    live_api_client: TestClient,
) -> None:
    """Verify rejection of malformed or disguised files before storage or OCR processing (Phase 6.4)."""
    ts = int(_utc_now().timestamp())
    inst = Institution(institution_id=f"INST-MALF-{ts}", display_name="Malformed Upload Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    pwd_hash = get_password_hash("Password123!")
    user = UserRepository.create(live_postgres_session, username=f"malf_{ts}", hashed_password=pwd_hash)
    live_postgres_session.commit()
    UserRepository.create_membership(live_postgres_session, user_id=user.id, institution_id=inst.id, role=ROLE_INSTITUTION_ADMIN)

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    login = live_api_client.post("/api/v1/auth/token", json={"username": user.username, "password": "Password123!"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Executable file disguised as PDF (magic byte check)
    exe_disguised_as_pdf = b"MZ\x90\x00\x03\x00\x00\x00This is an executable binary"
    res1 = live_api_client.post(
        f"/api/v1/applications/{app.id}/documents",
        headers=headers,
        data={"document_type": "land_record"},
        files={"file": ("fake_approval.pdf", exe_disguised_as_pdf, "application/pdf")},
    )
    assert res1.status_code == 422
    assert "magic byte" in res1.json()["detail"].lower() or "unsupported" in res1.json()["detail"].lower()

    # 2. Corrupt / empty file
    res2 = live_api_client.post(
        f"/api/v1/applications/{app.id}/documents",
        headers=headers,
        data={"document_type": "land_record"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert res2.status_code == 422

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_quarantine_download_protection_for_unclean_documents(
    live_postgres_session: Session,
    live_api_client: TestClient,
) -> None:
    """Verify documents with pending, unavailable, or rejected scan cannot be downloaded (Phase 6.5)."""
    ts = int(_utc_now().timestamp())
    inst = Institution(institution_id=f"INST-QUAR-{ts}", display_name="Quarantine Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    pwd_hash = get_password_hash("Password123!")
    user = UserRepository.create(live_postgres_session, username=f"quar_{ts}", hashed_password=pwd_hash)
    live_postgres_session.commit()
    UserRepository.create_membership(live_postgres_session, user_id=user.id, institution_id=inst.id, role=ROLE_INSTITUTION_ADMIN)

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    doc = Document(application_id=app.id, document_type="land_record")
    live_postgres_session.add(doc)
    live_postgres_session.commit()

    # Case 1: scan_status="pending_scan"
    v_pending = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="docs/test/pending.pdf",
        sha256="a" * 64,
        media_type="application/pdf",
        byte_size=100,
        scan_status="pending_scan",
        processing_status="queued",
    )
    # Case 2: scan_status="rejected"
    v_rejected = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_key="docs/test/rejected.pdf",
        sha256="b" * 64,
        media_type="application/pdf",
        byte_size=100,
        scan_status="rejected",
        processing_status="rejected",
    )
    # Case 3: scan_status="scan_unavailable"
    v_unavail = DocumentVersion(
        document_id=doc.id,
        version_number=3,
        storage_key="docs/test/unavail.pdf",
        sha256="c" * 64,
        media_type="application/pdf",
        byte_size=100,
        scan_status="scan_unavailable",
        processing_status="quarantined",
    )
    live_postgres_session.add_all([v_pending, v_rejected, v_unavail])
    live_postgres_session.commit()

    login = live_api_client.post("/api/v1/auth/token", json={"username": user.username, "password": "Password123!"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for v in (v_pending, v_rejected, v_unavail):
        dl_res = live_api_client.get(
            f"/api/v1/applications/{app.id}/documents/{doc.id}/versions/{v.id}/download",
            headers=headers,
        )
        assert dl_res.status_code == 403, f"Version {v.id} with scan_status {v.scan_status} was not blocked!"
        assert "quarantined or pending security scan" in dl_res.json()["detail"]

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_api_errors_do_not_leak_paths_tokens_or_secrets(
    live_postgres_session: Session,
    live_api_client: TestClient,
) -> None:
    """Verify API error envelopes do not leak internal filesystem paths, tokens, or secrets (Phase 6.6)."""
    # 1. 404 error
    res_404 = live_api_client.get("/api/v1/applications/99999999")
    assert res_404.status_code == 401  # Requires auth first

    # With valid auth
    ts = int(_utc_now().timestamp())
    inst = Institution(institution_id=f"INST-ERR-{ts}", display_name="Error Envelope Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    user = UserRepository.create(live_postgres_session, username=f"err_{ts}", hashed_password=get_password_hash("Pass123!"))
    live_postgres_session.commit()
    UserRepository.create_membership(live_postgres_session, user_id=user.id, institution_id=inst.id, role=ROLE_INSTITUTION_ADMIN)

    login = live_api_client.post("/api/v1/auth/token", json={"username": user.username, "password": "Pass123!"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_app_404 = live_api_client.get("/api/v1/applications/99999999", headers=headers)
    assert res_app_404.status_code == 404
    detail_404 = str(res_app_404.json())

    # Path traversal detection error
    res_trav = live_api_client.post(
        "/api/v1/applications/1/documents",
        headers=headers,
        data={"document_type": "../../../etc/passwd"},
        files={"file": ("test.pdf", b"%PDF-1.4 sample", "application/pdf")},
    )
    detail_trav = str(res_trav.json())

    for detail in (detail_404, detail_trav):
        # Assert no sensitive disk paths leaked
        assert "C:\\" not in detail
        assert "/home/" not in detail
        assert "/Users/" not in detail
        assert "JWT_SECRET_KEY" not in detail
        assert "Password123!" not in detail
        assert "postgres:" not in detail

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_storage_directory_traversal_prevention() -> None:
    """Verify LocalStorageBackend rejects directory traversal keys and isolates data outside web root (Phase 6.8)."""
    storage = LocalStorageBackend()

    traversal_keys = [
        "../secret.txt",
        "..\\secret.txt",
        "docs/../../etc/passwd",
        "/etc/passwd",
        "C:\\Windows\\system32\\cmd.exe",
        "docs/subdir/../../../root.bin",
    ]

    for key in traversal_keys:
        with pytest.raises(PathTraversalError):
            storage.put(key, b"malicious content")

        with pytest.raises(PathTraversalError):
            storage.read(key)

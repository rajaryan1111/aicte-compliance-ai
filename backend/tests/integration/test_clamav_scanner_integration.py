"""Integration test for live ClamAV daemon (Phase 2 & Phase 8).

Verifies real TCP socket communication with ClamAV daemon via INSTREAM protocol,
accurately distinguishing clean PDFs from EICAR test malware signatures.
If the daemon is unavailable, clearly skips and records that ClamAV remained unverified.
"""

from __future__ import annotations

import pytest

from backend.app.core.scanner import ClamAVScanner, ScanStatus
from backend.tests.integration.conftest import CLAMAV_HOST, CLAMAV_PORT, is_clamav_available


def test_live_clamav_daemon_eicar_and_clean_detection() -> None:
    """Verify live ClamAV daemon accurately classifies clean files and EICAR malware."""
    available, reason = is_clamav_available(CLAMAV_HOST, CLAMAV_PORT)
    if not available:
        pytest.skip(
            f"Live ClamAV daemon at {CLAMAV_HOST}:{CLAMAV_PORT} is not reachable: {reason}. "
            "Live ClamAV integration remains unverified in this test run."
        )

    scanner = ClamAVScanner(host=CLAMAV_HOST, port=CLAMAV_PORT)

    # 1. Clean synthetic document bytes
    clean_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    clean_res = scanner.scan(clean_bytes, "clean.pdf")
    assert clean_res.status == ScanStatus.CLEAN

    # 2. EICAR Standard Anti-Virus Test File
    eicar_bytes = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    malware_res = scanner.scan(eicar_bytes, "eicar.com")
    assert malware_res.status == ScanStatus.REJECTED
    assert "FOUND" in (malware_res.details or "") or "eicar" in (malware_res.details or "").lower()

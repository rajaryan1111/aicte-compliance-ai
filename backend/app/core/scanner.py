"""Malware scanning boundary and quarantine policy enforcement.

Ensures untrusted uploads never bypass scanning and fails safe (quarantine)
when an external scanner is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os
import socket
from typing import Protocol


class ScanStatus(StrEnum):
    PENDING_SCAN = "pending_scan"
    SCANNING = "scanning"
    CLEAN = "clean"
    REJECTED = "rejected"
    SCAN_UNAVAILABLE = "scan_unavailable"


@dataclass(frozen=True)
class ScanResult:
    """Outcome of a malware scan."""

    status: ScanStatus
    scanner_name: str
    details: str | None = None


class MalwareScanner(Protocol):
    """Protocol for pluggable malware scanners."""

    def scan(self, data: bytes, filename: str | None = None) -> ScanResult:
        """Scan file data for malware. Fails safe by never reporting clean on error."""


class ClamAVScanner:
    """ClamAV clamd daemon client via INSTREAM socket protocol."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.host = host or os.getenv("CLAMAV_HOST")
        port_env = os.getenv("CLAMAV_PORT")
        self.port = port or (int(port_env) if port_env else 3310)
        self.timeout = timeout_seconds

    def scan(self, data: bytes, filename: str | None = None) -> ScanResult:
        """Stream bytes to ClamAV daemon via INSTREAM command."""
        if not self.host:
            return ScanResult(
                status=ScanStatus.SCAN_UNAVAILABLE,
                scanner_name="clamav",
                details="ClamAV host is not configured; document kept in quarantine.",
            )

        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(b"zINSTREAM\0")
                # Send chunks prefixed by 4-byte big-endian length
                chunk_size = 64 * 1024
                offset = 0
                while offset < len(data):
                    chunk = data[offset : offset + chunk_size]
                    sock.sendall(len(chunk).to_bytes(4, byteorder="big") + chunk)
                    offset += len(chunk)
                # Send 0-length chunk to terminate stream
                sock.sendall((0).to_bytes(4, byteorder="big"))

                response = b""
                while True:
                    part = sock.recv(4096)
                    if not part:
                        break
                    response += part

                resp_str = response.decode("utf-8", errors="replace").strip()
                if "OK" in resp_str:
                    return ScanResult(
                        status=ScanStatus.CLEAN,
                        scanner_name="clamav",
                        details=resp_str,
                    )
                if "FOUND" in resp_str:
                    return ScanResult(
                        status=ScanStatus.REJECTED,
                        scanner_name="clamav",
                        details=resp_str,
                    )
                return ScanResult(
                    status=ScanStatus.SCAN_UNAVAILABLE,
                    scanner_name="clamav",
                    details=f"Inconclusive response from ClamAV: {resp_str}",
                )
        except (TimeoutError, socket.timeout):
            return ScanResult(
                status=ScanStatus.SCAN_UNAVAILABLE,
                scanner_name="clamav",
                details="ClamAV daemon scan timed out; document kept in quarantine.",
            )
        except Exception as exc:
            return ScanResult(
                status=ScanStatus.SCAN_UNAVAILABLE,
                scanner_name="clamav",
                details=f"ClamAV connection failure: {exc}",
            )


class QuarantineScanner:
    """Default fallback scanner when no external malware engine is configured.

    Fails safe: never claims clean; marks the file as scan_unavailable so it stays quarantined.
    """

    def scan(self, data: bytes, filename: str | None = None) -> ScanResult:
        return ScanResult(
            status=ScanStatus.SCAN_UNAVAILABLE,
            scanner_name="quarantine_default",
            details="No active scanning daemon configured. File remains quarantined pending security scan.",
        )


_default_scanner: MalwareScanner | None = None


def get_malware_scanner() -> MalwareScanner:
    """Retrieve singleton malware scanner."""
    global _default_scanner
    if _default_scanner is None:
        if os.getenv("CLAMAV_HOST"):
            _default_scanner = ClamAVScanner()
        else:
            _default_scanner = QuarantineScanner()
    return _default_scanner


def set_malware_scanner(scanner: MalwareScanner | None) -> None:
    """Override singleton scanner (for dependency injection / testing)."""
    global _default_scanner
    _default_scanner = scanner

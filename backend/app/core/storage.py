"""Private file storage abstraction and local filesystem implementation.

Enforces opaque server-side storage keys, directory traversal protections,
and storage outside the public web root.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Protocol
import uuid


class StorageError(Exception):
    """Base exception for storage operations."""


class StorageNotFoundError(StorageError):
    """Raised when a requested storage key does not exist."""


class PathTraversalError(StorageError):
    """Raised when a storage key attempts to escape the root directory."""


class StorageBackend(Protocol):
    """Protocol for secure, private document storage."""

    def put(self, storage_key: str, data: bytes) -> int:
        """Write bytes to the given storage key. Returns number of bytes written."""

    def read(self, storage_key: str) -> bytes:
        """Read bytes for the given storage key."""

    def delete(self, storage_key: str) -> bool:
        """Delete object for the storage key if it exists. Returns True if deleted."""

    def exists(self, storage_key: str) -> bool:
        """Check whether object exists at the given storage key."""


def generate_storage_key(
    sha256: str | None = None,
    extension: str | None = None,
) -> str:
    """Generate an opaque, unpredictable storage key without user or tenant metadata.

    Format: docs/{prefix}/{uuid_hex}{ext}
    """
    token = uuid.uuid4().hex
    prefix = (sha256[:2] if sha256 and len(sha256) >= 2 else token[:2]).lower()
    clean_ext = ""
    if extension:
        ext_clean = extension.lstrip(".").lower()
        if ext_clean in {"pdf", "jpg", "jpeg", "png", "tiff", "webp", "zip"}:
            clean_ext = f".{ext_clean}"
    return f"docs/{prefix}/{token}{clean_ext}"


class LocalStorageBackend:
    """Private filesystem storage backend with directory traversal prevention."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is not None:
            self.base_dir = Path(base_dir).resolve()
        else:
            configured = os.getenv("STORAGE_LOCAL_DIR")
            if configured:
                self.base_dir = Path(configured).resolve()
            else:
                self.base_dir = (Path(tempfile.gettempdir()) / "aicte_private_storage").resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, storage_key: str) -> Path:
        """Resolve storage key securely, ensuring it resides inside base_dir."""
        if not storage_key or not isinstance(storage_key, str) or not storage_key.strip():
            raise PathTraversalError("Storage key must be a non-empty string.")

        # Reject absolute paths and leading slashes/backslashes
        if storage_key.startswith(("/", "\\")) or os.path.isabs(storage_key):
            raise PathTraversalError(f"Absolute path not permitted in storage key: {storage_key!r}")

        # Reject directory traversal components
        parts = storage_key.replace("\\", "/").split("/")
        if any(p in {"..", "."} for p in parts if p):
            raise PathTraversalError(f"Directory traversal detected in storage key: {storage_key!r}")

        target_path = (self.base_dir / storage_key.replace("\\", "/")).resolve()

        # Enforce that target_path is strictly inside base_dir
        try:
            target_path.relative_to(self.base_dir)
        except ValueError as exc:
            raise PathTraversalError(
                f"Storage key resolves outside root directory: {storage_key!r}"
            ) from exc

        return target_path

    def put(self, storage_key: str, data: bytes) -> int:
        """Atomically write data to target path using a temporary sibling file."""
        if not isinstance(data, bytes):
            raise StorageError("Storage data must be bytes.")

        target = self._resolve_key(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write pattern: write to tmp file then atomic rename/replace
        tmp_fd, tmp_path_str = tempfile.mkstemp(dir=target.parent, prefix=".tmp_upload_")
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(data)
            tmp_path.replace(target)
            return len(data)
        except Exception as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise StorageError(f"Failed to write storage key {storage_key!r}: {exc}") from exc

    def read(self, storage_key: str) -> bytes:
        """Read data for the given storage key."""
        target = self._resolve_key(storage_key)
        if not target.is_file():
            raise StorageNotFoundError(f"Storage key not found: {storage_key!r}")
        try:
            return target.read_bytes()
        except Exception as exc:
            raise StorageError(f"Failed to read storage key {storage_key!r}: {exc}") from exc

    def delete(self, storage_key: str) -> bool:
        """Delete stored file if present."""
        target = self._resolve_key(storage_key)
        if target.is_file():
            target.unlink()
            return True
        return False

    def exists(self, storage_key: str) -> bool:
        """Check whether file exists."""
        try:
            target = self._resolve_key(storage_key)
            return target.is_file()
        except PathTraversalError:
            return False


_default_storage_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return configured singleton StorageBackend."""
    global _default_storage_backend
    if _default_storage_backend is None:
        _default_storage_backend = LocalStorageBackend()
    return _default_storage_backend


def set_storage_backend(backend: StorageBackend | None) -> None:
    """Override singleton storage backend (for testing)."""
    global _default_storage_backend
    _default_storage_backend = backend

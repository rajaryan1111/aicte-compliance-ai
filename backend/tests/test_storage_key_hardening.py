"""Regression tests: Windows drive-qualified storage keys are rejected on POSIX.

``LocalStorageBackend._resolve_key`` previously relied on ``os.path.isabs()`` to
reject absolute keys. On a POSIX host ``C:\\Windows\\system32\\cmd.exe`` is not
absolute, so the key was treated as an ordinary filename and the traversal test
in ``backend/tests/integration/test_security_and_failure_paths.py`` failed on
Linux while passing on Windows. Containment was never violated (the resolved
path stayed inside the storage root), but the refusal depended on the host OS.

The fix rejects drive-qualified keys on every platform. These tests pin that
behaviour and, equally importantly, that legitimate keys still work.
"""

from __future__ import annotations

import pytest

from backend.app.core.storage import (
    LocalStorageBackend,
    PathTraversalError,
    generate_storage_key,
)


@pytest.fixture
def storage(tmp_path):
    return LocalStorageBackend(base_dir=tmp_path)


# --- Windows drive-qualified keys: rejected regardless of host OS ---

WINDOWS_ABSOLUTE_KEYS = [
    "C:\\Windows\\system32\\cmd.exe",
    "c:\\windows\\system32\\cmd.exe",
    "C:/Windows/system32/cmd.exe",
    "Z:secret.txt",
    "c:autoexec.bat",
    "C:",
]


@pytest.mark.parametrize("key", WINDOWS_ABSOLUTE_KEYS)
def test_drive_qualified_keys_are_rejected(storage: LocalStorageBackend, key: str) -> None:
    with pytest.raises(PathTraversalError):
        storage.put(key, b"malicious content")
    with pytest.raises(PathTraversalError):
        storage.read(key)
    with pytest.raises(PathTraversalError):
        storage.delete(key)
    # exists() deliberately reports an unsafe key as absent instead of raising;
    # that is existing public behaviour and is preserved here, not changed.
    assert storage.exists(key) is False


@pytest.mark.parametrize(
    "key",
    [
        # POSIX-style traversal.
        "../secret.txt",
        "docs/../../etc/passwd",
        "docs/subdir/../../../root.bin",
        # Windows backslash separators, same intent.
        "..\\secret.txt",
        "docs\\..\\..\\etc\\passwd",
        # Absolute and UNC forms.
        "/etc/passwd",
        "\\\\server\\share\\file.txt",
        # Current-directory components.
        "./docs/file.pdf",
        "docs/./file.pdf",
    ],
)
def test_traversal_attempts_are_rejected(storage: LocalStorageBackend, key: str) -> None:
    with pytest.raises(PathTraversalError):
        storage.put(key, b"x")


# --- Legitimate keys must keep working ---

VALID_KEYS = [
    "docs/ab/" + "0" * 32 + ".pdf",
    "docs/ab/" + "1" * 32 + ".png",
    "docs/ab/nested/deeper/" + "2" * 32 + ".pdf",
    "docs\\ab\\" + "3" * 32 + ".pdf",  # existing backslash normalisation is preserved
    "docs/ab/plain_name-with.dots.v2.pdf",
]


@pytest.mark.parametrize("key", VALID_KEYS)
def test_valid_keys_round_trip(storage: LocalStorageBackend, key: str) -> None:
    assert storage.put(key, b"payload") == len(b"payload")
    assert storage.read(key) == b"payload"
    assert storage.exists(key) is True


def test_valid_keys_stay_inside_storage_root(storage: LocalStorageBackend) -> None:
    for key in VALID_KEYS:
        resolved = storage._resolve_key(key)
        assert resolved.is_relative_to(storage.base_dir), key


def test_generated_keys_are_accepted_and_contained(storage: LocalStorageBackend) -> None:
    """Keys produced by generate_storage_key() must never trip the new guard."""
    for extension in (None, "pdf", "jpeg", "tiff"):
        key = generate_storage_key(sha256="ab" + "0" * 62, extension=extension)
        assert storage.put(key, b"x") == 1
        assert storage.read(key) == b"x"
        assert storage._resolve_key(key).is_relative_to(storage.base_dir)


def test_drive_prefix_is_refused_in_any_component(storage: LocalStorageBackend) -> None:
    """A drive prefix or colon is refused wherever it appears, not only at the start."""
    with pytest.raises(PathTraversalError):
        storage.put("docs/C:\\Windows\\system32\\cmd.exe", b"x")
    with pytest.raises(PathTraversalError):
        storage.put("docs\\D:\\data\\file.pdf", b"x")
    with pytest.raises(PathTraversalError):
        storage.put("docs/ab/stream.pdf:hidden", b"x")


def test_rejection_message_identifies_the_reason(storage: LocalStorageBackend) -> None:
    with pytest.raises(PathTraversalError, match="Windows path syntax"):
        storage.put("C:\\Windows\\system32\\cmd.exe", b"x")

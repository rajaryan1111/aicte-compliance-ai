"""Tests for private document storage abstraction, opaque keys, and traversal defense."""

from __future__ import annotations

import tempfile

import pytest

from backend.app.core.storage import (
    LocalStorageBackend,
    PathTraversalError,
    StorageNotFoundError,
    generate_storage_key,
)


@pytest.fixture
def temp_storage():
    """Isolated temporary storage directory for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield LocalStorageBackend(base_dir=tmp_dir)


def test_put_read_delete_exists_lifecycle(temp_storage: LocalStorageBackend):
    """Test standard storage operations lifecycle."""
    key = generate_storage_key(sha256="abcd" * 16, extension="pdf")
    data = b"%PDF-1.4 sample file content"

    assert not temp_storage.exists(key)

    # 1. Put
    bytes_written = temp_storage.put(key, data)
    assert bytes_written == len(data)
    assert temp_storage.exists(key)

    # 2. Read
    read_data = temp_storage.read(key)
    assert read_data == data

    # 3. Delete
    deleted = temp_storage.delete(key)
    assert deleted is True
    assert not temp_storage.exists(key)

    # 4. Read after delete raises StorageNotFoundError
    with pytest.raises(StorageNotFoundError):
        temp_storage.read(key)


def test_opaque_storage_keys_unpredictable():
    """Verify that storage keys are opaque, lower-case, and do not include user/tenant info."""
    key1 = generate_storage_key(sha256="0123456789abcdef" * 4, extension="jpg")
    key2 = generate_storage_key(sha256="0123456789abcdef" * 4, extension="jpg")

    assert key1 != key2
    assert key1.startswith("docs/01/")
    assert key2.startswith("docs/01/")
    assert key1.endswith(".jpg")
    assert "user" not in key1.lower()
    assert "inst" not in key1.lower()


def test_path_traversal_attempts_rejected(temp_storage: LocalStorageBackend):
    """Verify rejection of directory traversal, parent paths, and escape sequences."""
    traversal_keys = [
        "../escaped.pdf",
        "docs/../../etc/passwd",
        "/etc/passwd",
        "docs/..\\..\\windows\\system32",
        "..",
        "",
    ]

    for bad_key in traversal_keys:
        with pytest.raises(PathTraversalError):
            temp_storage.put(bad_key, b"data")

        with pytest.raises(PathTraversalError):
            temp_storage.read(bad_key)

        assert not temp_storage.exists(bad_key)


def test_read_missing_key_raises_storage_not_found(temp_storage: LocalStorageBackend):
    """Attempting to read a non-existent key raises StorageNotFoundError."""
    missing_key = "docs/ab/nonexistent_file.pdf"
    with pytest.raises(StorageNotFoundError):
        temp_storage.read(missing_key)

"""Regression tests for image pre-checks (byte cap, pixel cap, format identity)."""
from __future__ import annotations

import hashlib
import io
import struct
import zlib

import pytest
from PIL import Image

from backend.app.ocr_pipeline import (
    MAX_IMAGE_PIXELS,
    MAX_UPLOAD_BYTES,
    OCRInputError,
    OCRRawResult,
    _validate_image_bytes,
    process_institution_document,
)


def image_bytes(format_name: str = "PNG", size: tuple[int, int] = (80, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=format_name)
    return buffer.getvalue()


def oversized_header_png(width: int, height: int) -> bytes:
    """A valid PNG header declaring huge dimensions without pixel data."""
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = (
        struct.pack(">I", len(header))
        + b"IHDR"
        + header
        + struct.pack(">I", zlib.crc32(b"IHDR" + header) & 0xFFFFFFFF)
    )
    return signature + chunk + b"\x00\x00\x00\x00IEND\xaeB`\x82"


def test_bytes_above_the_cap_are_rejected_before_decoding():
    with pytest.raises(OCRInputError, match="10 MiB"):
        _validate_image_bytes(b"\x00" * (MAX_UPLOAD_BYTES + 1))


def test_empty_and_non_bytes_inputs_are_rejected():
    with pytest.raises(OCRInputError, match="non-empty"):
        _validate_image_bytes(b"")
    with pytest.raises(OCRInputError, match="non-empty"):
        _validate_image_bytes(bytearray(b"abc"))  # type: ignore[arg-type]


def test_pixel_count_above_the_cap_is_rejected_from_the_header():
    payload = oversized_header_png(10_000, 4_000)  # 40 MP, small file

    assert len(payload) < 1024
    with pytest.raises(OCRInputError, match="pixel count"):
        _validate_image_bytes(payload)


def test_absurd_declared_dimensions_are_rejected_before_any_decode():
    payload = oversized_header_png(100_000, 100_000)

    with pytest.raises(OCRInputError):
        _validate_image_bytes(payload)


def test_pixel_cap_boundary_is_documented_and_enforced():
    width = 10_000
    height = MAX_IMAGE_PIXELS // width + 1
    with pytest.raises(OCRInputError, match="pixel count"):
        _validate_image_bytes(oversized_header_png(width, height))


def test_source_hash_is_deterministic_for_identical_bytes():
    payload = image_bytes()

    class EmptyEngine:
        def recognize(self, image_bytes: bytes) -> OCRRawResult:
            return OCRRawResult((), "fake-test-engine", "1.0")

    first = process_institution_document(payload, EmptyEngine())
    second = process_institution_document(payload, EmptyEngine())

    assert first.source_sha256 == hashlib.sha256(payload).hexdigest()
    assert first.source_sha256 == second.source_sha256
    assert first.warnings == second.warnings


def test_unsupported_format_is_rejected_without_engine_call():
    class CountingEngine:
        calls = 0

        def recognize(self, image_bytes: bytes) -> OCRRawResult:
            CountingEngine.calls += 1
            return OCRRawResult((), "fake-test-engine")

    with pytest.raises(OCRInputError, match="Unsupported"):
        process_institution_document(image_bytes("GIF"), CountingEngine())

    assert CountingEngine.calls == 0


def test_pdf_input_is_rejected_as_unsupported_before_engine_call():
    class CountingEngine:
        calls = 0

        def recognize(self, image_bytes: bytes) -> OCRRawResult:
            CountingEngine.calls += 1
            return OCRRawResult((), "fake-test-engine")

    with pytest.raises(OCRInputError):
        process_institution_document(b"%PDF-1.4\n%synthetic\n", CountingEngine())

    assert CountingEngine.calls == 0

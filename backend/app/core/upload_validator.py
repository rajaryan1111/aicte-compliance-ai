"""File validation, size limits, format detection, and resource constraint enforcement.

Protects the processing pipeline against oversized payloads, format spoofing,
decompression bombs, malformed structures, and password-protected PDFs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import re
from typing import BinaryIO

from PIL import Image

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_IMAGE_PIXELS = 30_000_000        # 30 Megapixels
MAX_PDF_PAGES = 50                   # 50 Pages maximum per submission
CHUNK_SIZE = 64 * 1024               # 64 KiB read chunks

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}


class UploadValidationError(ValueError):
    """Base exception for file intake validation failures."""


class FileTooLargeError(UploadValidationError):
    """Raised when file exceeds the maximum permitted byte size."""


class EmptyFileError(UploadValidationError):
    """Raised when uploaded file contains 0 bytes."""


class UnsupportedMediaTypeError(UploadValidationError):
    """Raised when format or magic signature is unsupported."""


class CorruptedFileError(UploadValidationError):
    """Raised when file fails structural or decompression validation."""


class DecompressionBombError(UploadValidationError):
    """Raised when image pixel dimensions exceed safe bounds."""


class EncryptedPDFError(UploadValidationError):
    """Raised when a PDF is password-protected or encrypted."""


@dataclass(frozen=True)
class ValidatedUpload:
    """Immutable validated upload payload ready for private storage and processing."""

    data: bytes
    byte_size: int
    sha256: str
    media_type: str
    file_name: str
    page_count: int | None = None


def sanitize_filename(filename: str | None) -> str:
    """Sanitize original client filename to a safe basename, max 255 chars."""
    if not filename or not isinstance(filename, str):
        return "unnamed_document"
    # Extract only the base name, removing directory components and traversal
    name = Path(filename).name
    # Remove control characters, null bytes
    clean = re.sub(r"[\x00-\x1f\x7f/\\]", "", name).strip()
    if not clean:
        return "unnamed_document"
    if len(clean) > 255:
        # Preserve extension if present
        parts = clean.rsplit(".", 1)
        if len(parts) == 2 and len(parts[1]) < 10:
            stem = parts[0][: 254 - len(parts[1])]
            clean = f"{stem}.{parts[1]}"
        else:
            clean = clean[:255]
    return clean


def detect_file_signature(data: bytes) -> str | None:
    """Inspect magic bytes to detect true file format."""
    if len(data) < 4:
        return None

    # PDF: %PDF-
    if data.startswith(b"%PDF-"):
        return "application/pdf"

    # JPEG: \xff\xd8\xff
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # PNG: \x89PNG\r\n\x1a\n
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    # TIFF: II*\x00 (little endian) or MM\x00* (big endian)
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return "image/tiff"

    # WEBP: RIFF....WEBP
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"

    return None


def read_stream_bounded(stream: BinaryIO, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read stream in chunks, enforcing strict byte limits and rejecting empty content."""
    buffer = io.BytesIO()
    total_read = 0

    while True:
        chunk = stream.read(CHUNK_SIZE)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_bytes:
            raise FileTooLargeError(
                f"File size exceeds maximum permitted limit of {max_bytes} bytes (10 MiB)."
            )
        buffer.write(chunk)

    data = buffer.getvalue()
    if not data:
        raise EmptyFileError("Uploaded file is empty (0 bytes).")
    return data


def validate_upload_bytes(
    data: bytes,
    filename: str | None = None,
    declared_content_type: str | None = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> ValidatedUpload:
    """Validate file bytes against size, signature, content structure and safety limits."""
    if not data:
        raise EmptyFileError("Uploaded file is empty (0 bytes).")

    byte_size = len(data)
    if byte_size > max_bytes:
        raise FileTooLargeError(
            f"File size {byte_size} exceeds maximum permitted limit of {max_bytes} bytes."
        )

    # 1. Magic bytes detection
    detected_mime = detect_file_signature(data)
    if not detected_mime or detected_mime not in SUPPORTED_MIME_TYPES:
        raise UnsupportedMediaTypeError(
            "Unsupported file format or invalid magic signature. "
            "Supported formats: PDF, JPEG, PNG, TIFF, WEBP."
        )

    # If client declared a content-type, ensure compatibility
    if declared_content_type:
        decl = declared_content_type.split(";")[0].strip().lower()
        if decl != "application/octet-stream" and decl in SUPPORTED_MIME_TYPES:
            if decl != detected_mime and not (decl == "image/jpg" and detected_mime == "image/jpeg"):
                raise UnsupportedMediaTypeError(
                    f"Declared content-type '{declared_content_type}' does not match "
                    f"detected signature '{detected_mime}'."
                )

    page_count: int | None = None
    safe_name = sanitize_filename(filename)

    # 2. Format-specific deep validation
    if detected_mime == "application/pdf":
        page_count = _validate_pdf_content(data)
    else:
        _validate_image_content(data, detected_mime)
        page_count = 1

    sha256_hash = hashlib.sha256(data).hexdigest()

    return ValidatedUpload(
        data=data,
        byte_size=byte_size,
        sha256=sha256_hash,
        media_type=detected_mime,
        file_name=safe_name,
        page_count=page_count,
    )


def _validate_image_content(data: bytes, expected_mime: str) -> None:
    """Verify image decode safety, dimensions, and decompression limit."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
            width, height = img.size
            if width <= 0 or height <= 0:
                raise CorruptedFileError("Image dimensions must be positive.")
            if width * height > MAX_IMAGE_PIXELS:
                raise DecompressionBombError(
                    f"Image total pixels ({width * height}) exceed maximum limit of {MAX_IMAGE_PIXELS}."
                )
    except (DecompressionBombError, CorruptedFileError):
        raise
    except Exception as exc:
        raise CorruptedFileError(f"Image structural validation failed: {exc}") from exc


def _validate_pdf_content(data: bytes) -> int:
    """Verify PDF parseability, encryption status, and page limit."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = pdf.pages
            count = len(pages)
            if count < 1:
                raise CorruptedFileError("PDF contains 0 valid pages.")
            if count > MAX_PDF_PAGES:
                raise CorruptedFileError(
                    f"PDF page count ({count}) exceeds maximum allowed limit of {MAX_PDF_PAGES}."
                )
            return count
    except CorruptedFileError:
        raise
    except Exception as exc:
        # Check if error is related to password or encryption
        err_msg = str(exc).lower()
        if "password" in err_msg or "encrypt" in err_msg:
            raise EncryptedPDFError(
                "Password-protected or encrypted PDFs cannot be processed safely."
            ) from exc
        raise CorruptedFileError(f"PDF structural parsing failed: {exc}") from exc

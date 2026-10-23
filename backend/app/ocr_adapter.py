"""Stable OCR adapter contract for the AICTE Compliance Assistant.

This module defines an application-owned boundary only. It deliberately has no
OCR engine dependency and does not import the fake-id-screening repository.
Implementations must be optional, reviewed and tested with synthetic documents.
OCR output is evidence for human review, never proof of authenticity/compliance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class OCRField:
    """One extracted field plus enough provenance for a reviewer to check it."""

    value: str | None
    confidence: float | None
    page_number: int | None = None
    evidence_text: str | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.page_number is not None and self.page_number < 1:
            raise ValueError("page_number must be a 1-based positive integer")
        if self.value is not None and not self.value.strip():
            raise ValueError("value must be non-blank or None")


@dataclass(frozen=True)
class OCRDocumentResult:
    """Advisory extraction result, separated from regulatory validation."""

    fields: dict[str, OCRField]
    engine: str
    engine_version: str | None = None
    source_sha256: str | None = None
    warnings: tuple[str, ...] = ()
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        if not self.engine.strip():
            raise ValueError("engine must be named")
        if not self.requires_human_review:
            raise ValueError("OCR results must always require human review")
        if self.source_sha256 is not None:
            value = self.source_sha256.lower()
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("source_sha256 must be a 64-character SHA-256 hex digest")


class OCRAdapter(Protocol):
    """Pluggable engine interface; implementations must not make regulatory decisions."""

    def extract(self, file_path: str) -> OCRDocumentResult:
        """Extract text/fields from an already validated local document."""


def parse_iso_date_candidate(value: str | None) -> date | None:
    """Parse only unambiguous ISO YYYY-MM-DD candidates; never guess day/month order."""
    if value is None:
        return None
    candidate = value.strip()
    if len(candidate) != 10:
        return None
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.isoformat() != candidate:
        return None
    return parsed

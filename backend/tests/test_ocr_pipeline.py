from __future__ import annotations

import io

import pytest
from PIL import Image

from backend.app.ocr_pipeline import (
    OCRInputError,
    OCRRawResult,
    OCRWord,
    extract_institution_fields,
    process_institution_document,
)


def image_bytes(format_name: str = "PNG", size: tuple[int, int] = (80, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=format_name)
    return buffer.getvalue()


class FakeEngine:
    def __init__(self, words: tuple[OCRWord, ...]):
        self.words = words
        self.calls = 0

    def recognize(self, image_bytes: bytes) -> OCRRawResult:
        self.calls += 1
        return OCRRawResult(self.words, "fake-test-engine", "1.0")


def test_extracts_context_labelled_english_institution_fields():
    fields = extract_institution_fields(
        "Institution Name: Example Technical Institute\n"
        "Certificate No: CERT-2026/0042\n"
        "Issue Date: 2026-04-30\n"
        "Valid Until: 2027-04-30\n"
        "Academic Year: 2026/2027",
        confidence=0.88,
        page_number=2,
    )
    assert fields["institution_name"].value == "Example Technical Institute"
    assert fields["certificate_number"].value == "CERT-2026/0042"
    assert fields["issue_date"].value == "2026-04-30"
    assert fields["valid_until"].value == "2027-04-30"
    assert fields["academic_year"].value == "2026-2027"
    assert fields["institution_name"].confidence == 0.88
    assert fields["institution_name"].page_number == 2
    assert fields["institution_name"].evidence_text.startswith("Institution Name:")


def test_extracts_supported_hindi_institution_fields():
    fields = extract_institution_fields(
        "संस्थान का नाम: उदाहरण तकनीकी संस्थान\n"
        "प्रमाणपत्र संख्या: CERT-2026-0042\n"
        "शैक्षणिक वर्ष: 2026-2027"
    )
    assert fields["institution_name"].value == "उदाहरण तकनीकी संस्थान"
    assert fields["certificate_number"].value == "CERT-2026-0042"
    assert fields["academic_year"].value == "2026-2027"


@pytest.mark.parametrize("ambiguous", ["30/04/2026", "04/30/2026", "2026-02-30", "April 2026"])
def test_ambiguous_or_invalid_dates_are_not_guessed(ambiguous):
    fields = extract_institution_fields(f"Valid Until: {ambiguous}", confidence=0.9)
    assert "valid_until" not in fields


def test_personal_identity_fields_are_not_extracted():
    fields = extract_institution_fields(
        "Name: Example Person\nDOB: 2000-01-01\n"
        "Student ID: 1234567890\nInstitution Name: Example College"
    )
    assert set(fields) == {"institution_name"}
    assert "name" not in fields
    assert "dob" not in fields
    assert "student_id" not in fields


def test_pipeline_preserves_line_boundaries_hash_and_human_review_gate():
    payload = image_bytes()
    engine = FakeEngine((
        OCRWord("Institution", 0.9, 1, 1),
        OCRWord("Name:", 0.9, 1, 1),
        OCRWord("Example", 0.9, 1, 1),
        OCRWord("College", 0.9, 1, 1),
        OCRWord("Certificate", 0.8, 1, 2),
        OCRWord("No:", 0.8, 1, 2),
        OCRWord("CERT-001", 0.8, 1, 2),
    ))
    result = process_institution_document(payload, engine)
    assert engine.calls == 1
    assert result.engine == "fake-test-engine"
    assert result.source_sha256 is not None and len(result.source_sha256) == 64
    assert result.requires_human_review is True
    assert result.fields["institution_name"].value == "Example College"
    assert result.fields["certificate_number"].value == "CERT-001"
    assert result.fields["certificate_number"].confidence == pytest.approx(0.8)


def test_pipeline_rejects_non_image_bytes_before_calling_engine():
    engine = FakeEngine(())
    with pytest.raises(OCRInputError):
        process_institution_document(b"not an image", engine)
    assert engine.calls == 0


def test_pipeline_rejects_unsupported_image_format():
    engine = FakeEngine(())
    payload = image_bytes("BMP")
    with pytest.raises(OCRInputError, match="Unsupported"):
        process_institution_document(payload, engine)
    assert engine.calls == 0


def test_engine_failure_is_not_silently_converted_to_success():
    class BrokenEngine:
        def recognize(self, image_bytes: bytes) -> OCRRawResult:
            raise RuntimeError("engine unavailable")

    with pytest.raises(RuntimeError, match="engine unavailable"):
        process_institution_document(image_bytes(), BrokenEngine())


def test_empty_engine_name_is_rejected():
    class UnnamedEngine:
        def recognize(self, image_bytes: bytes) -> OCRRawResult:
            return OCRRawResult((), " ")

    with pytest.raises(ValueError, match="non-empty"):
        process_institution_document(image_bytes(), UnnamedEngine())


@pytest.mark.parametrize("academic_year", ["2027-2026", "2026-2026"])
def test_reversed_or_zero_length_academic_year_is_not_extracted(academic_year):
    fields = extract_institution_fields(f"Academic Year: {academic_year}")
    assert "academic_year" not in fields


def test_duplicate_field_labels_keep_first_value_deterministically():
    fields = extract_institution_fields(
        "Institution Name: First Example College\n"
        "Institution Name: Second Example College"
    )
    assert fields["institution_name"].value == "First Example College"


def test_oversized_ocr_text_is_rejected_before_regex_extraction():
    from backend.app.ocr_pipeline import MAX_OCR_TEXT_CHARS

    with pytest.raises(ValueError, match="processing limit"):
        extract_institution_fields("x" * (MAX_OCR_TEXT_CHARS + 1))


def test_non_string_ocr_text_is_rejected_explicitly():
    with pytest.raises(TypeError, match="must be a string"):
        extract_institution_fields(None)

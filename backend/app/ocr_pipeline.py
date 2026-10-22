"""Optional OCR pipeline for institutional compliance documents.

This application-owned module does not import the fake-id-screening repository.
OCR output is evidence for human review, never proof of authenticity/compliance.
Install backend/requirements-ocr.txt and the Tesseract system binary to use the
optional Tesseract adapter.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Protocol

from backend.app.ocr_adapter import OCRDocumentResult, OCRField, parse_iso_date_candidate

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 30_000_000
MAX_OCR_TEXT_CHARS = 100_000
SUPPORTED_FORMATS = {"JPEG", "PNG", "TIFF", "WEBP"}


class OCRInputError(ValueError):
    """Raised when an input image is unsafe, unsupported or too large."""


@dataclass(frozen=True)
class OCRWord:
    text: str
    confidence: float
    page_number: int = 1
    line_number: int = 1


@dataclass(frozen=True)
class OCRRawResult:
    words: tuple[OCRWord, ...]
    engine: str
    engine_version: str | None = None
    warnings: tuple[str, ...] = ()


class RawOCREngine(Protocol):
    def recognize(self, image_bytes: bytes) -> OCRRawResult:
        """Recognize text from validated image bytes; make no compliance decision."""


def _validate_image_bytes(image_bytes: bytes) -> None:
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise OCRInputError("A non-empty image byte sequence is required.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise OCRInputError("Image exceeds the 10 MiB processing limit.")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "OCR image support is optional. Install backend/requirements-ocr.txt."
        ) from exc
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format not in SUPPORTED_FORMATS:
                raise OCRInputError("Unsupported image format.")
            if image.width < 1 or image.height < 1:
                raise OCRInputError("Image dimensions are invalid.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise OCRInputError("Image pixel count exceeds the safety limit.")
            image.verify()
    except OCRInputError:
        raise
    except Exception as exc:
        raise OCRInputError("Image could not be decoded safely.") from exc


def _normalised_confidence(words: tuple[OCRWord, ...]) -> float | None:
    valid = [
        max(0.0, min(1.0, word.confidence))
        for word in words
        if word.confidence >= 0
    ]
    return sum(valid) / len(valid) if valid else None


def extract_institution_fields(
    text: str,
    confidence: float | None = None,
    page_number: int = 1,
) -> dict[str, OCRField]:
    """Extract context-labelled institution fields in English or Hindi.

    Dates are accepted only in strict ISO YYYY-MM-DD form. Ambiguous dates are
    left unresolved rather than guessing day/month order. Personal identity
    fields are deliberately outside this extractor's scope.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if len(text) > MAX_OCR_TEXT_CHARS:
        raise ValueError(f"OCR text exceeds the {MAX_OCR_TEXT_CHARS}-character processing limit")
    if not text or not text.strip():
        return {}
    if page_number < 1:
        raise ValueError("page_number must be a positive 1-based integer")
    confidence = None if confidence is None else max(0.0, min(1.0, confidence))
    fields: dict[str, OCRField] = {}
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("institution_name", re.compile(r"^(?:name of institution|institution name|name of college|college name|संस्थान का नाम|संस्था का नाम|महाविद्यालय का नाम|कॉलेज का नाम)\s*[:\-]\s*(.{3,160})$", re.I)),
        ("certificate_number", re.compile(r"^(?:certificate no\.?|certificate number|reference no\.?|reference number|document no\.?|प्रमाणपत्र संख्या|प्रमाणपत्र क्रमांक|संदर्भ संख्या|दस्तावेज़ संख्या)\s*[:\-]\s*([A-Z0-9][A-Z0-9/._\-]{1,79})$", re.I)),
        ("application_reference", re.compile(r"^(?:application ref(?:erence)?|application id|application no\.?|आवेदन संदर्भ|आवेदन संख्या|आवेदन क्रमांक)\s*[:\-]\s*([A-Z0-9][A-Z0-9/._\-]{1,79})$", re.I)),
        ("issue_date", re.compile(r"^(?:date of issue|issued on|issue date|जारी करने की तिथि|जारी दिनांक|निर्गमन तिथि)\s*[:\-]\s*(.+)$", re.I)),
        ("valid_until", re.compile(r"^(?:valid until|valid up to|valid upto|valid till|expiry date|expires on|वैधता तक|समाप्ति तिथि|अंतिम वैधता तिथि)\s*[:\-]\s*(.+)$", re.I)),
        ("academic_year", re.compile(r"^(?:academic year|academic session|शैक्षणिक वर्ष|शैक्षिक सत्र)\s*[:\-]\s*((?:20\d{2})\s*[-/]\s*(?:20\d{2}))$", re.I)),
    )

    for line in lines:
        for field_name, pattern in patterns:
            match = pattern.match(line)
            if not match or field_name in fields:
                continue
            raw_value = match.group(1).strip()
            if field_name in {"issue_date", "valid_until"}:
                parsed_date = parse_iso_date_candidate(raw_value)
                if parsed_date is None:
                    continue
                raw_value = parsed_date.isoformat()
            elif field_name == "academic_year":
                normalized_year = re.sub(r"\s+", "", raw_value).replace("/", "-")
                start_year, end_year = (int(part) for part in normalized_year.split("-"))
                if end_year <= start_year:
                    continue
                raw_value = normalized_year
            fields[field_name] = OCRField(
                value=raw_value,
                confidence=confidence,
                page_number=page_number,
                evidence_text=line[:500],
            )
    return fields


class TesseractOCRAdapter:
    """Lazy optional Tesseract adapter; requires Pillow, pytesseract and Tesseract."""

    def __init__(self, language: str = "eng", max_bytes: int = MAX_UPLOAD_BYTES) -> None:
        if not language or not re.fullmatch(r"[A-Za-z_+.-]{2,32}", language):
            raise ValueError("language must be a safe Tesseract language code")
        if not 1 <= max_bytes <= MAX_UPLOAD_BYTES:
            raise ValueError("max_bytes must be between 1 byte and 10 MiB")
        self.language = language
        self.max_bytes = max_bytes

    def recognize(self, image_bytes: bytes) -> OCRRawResult:
        _validate_image_bytes(image_bytes)
        if len(image_bytes) > self.max_bytes:
            raise OCRInputError("Image exceeds the configured processing limit.")
        try:
            import pytesseract
            from PIL import Image, ImageOps
            from pytesseract import Output
        except ImportError as exc:
            raise RuntimeError(
                "OCR dependencies are optional. Install backend/requirements-ocr.txt."
            ) from exc

        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source.load()
                image = ImageOps.grayscale(source)
                image = ImageOps.autocontrast(image)
                if min(image.size) < 700:
                    scale = min(2.0, 700 / max(1, min(image.size)))
                    new_size = (
                        max(1, int(image.width * scale)),
                        max(1, int(image.height * scale)),
                    )
                    if new_size[0] * new_size[1] <= MAX_IMAGE_PIXELS:
                        image = image.resize(new_size)
                data = pytesseract.image_to_data(
                    image, lang=self.language, config="--psm 6", output_type=Output.DICT
                )
        except Exception as exc:
            raise RuntimeError("Tesseract OCR failed; no result was produced.") from exc

        words: list[OCRWord] = []
        text_values = data.get("text", [])
        confidences = data.get("conf", [])
        page_values = data.get("page_num", [])
        line_values = data.get("line_num", [])
        for i, (raw_text, raw_conf) in enumerate(zip(text_values, confidences)):
            word = str(raw_text).strip()
            try:
                conf = float(raw_conf) / 100.0
            except (TypeError, ValueError):
                continue
            if not word or conf < 0:
                continue
            try:
                page_number = max(1, int(page_values[i])) if i < len(page_values) else 1
                line_number = max(1, int(line_values[i])) if i < len(line_values) else 1
            except (TypeError, ValueError):
                page_number, line_number = 1, 1
            words.append(
                OCRWord(
                    text=word,
                    confidence=max(0.0, min(1.0, conf)),
                    page_number=page_number,
                    line_number=line_number,
                )
            )
        try:
            version = str(pytesseract.get_tesseract_version()).splitlines()[0]
        except Exception:
            version = None
        return OCRRawResult(tuple(words), "tesseract", version)


def process_institution_document(
    image_bytes: bytes,
    engine: RawOCREngine,
) -> OCRDocumentResult:
    """Validate, OCR and extract institution-document fields for human review."""
    _validate_image_bytes(image_bytes)
    raw = engine.recognize(image_bytes)
    if not raw.engine.strip():
        raise ValueError("OCR engine must return a non-empty name.")

    grouped: dict[tuple[int, int], list[OCRWord]] = {}
    for word in raw.words:
        if not word.text.strip() or word.confidence < 0:
            continue
        if word.page_number < 1 or word.line_number < 1:
            continue
        grouped.setdefault((word.page_number, word.line_number), []).append(word)

    fields: dict[str, OCRField] = {}
    for (page_number, _line_number), line_words in sorted(grouped.items()):
        line_text = " ".join(word.text for word in line_words)
        line_confidence = _normalised_confidence(tuple(line_words))
        extracted = extract_institution_fields(line_text, line_confidence, page_number)
        for field_name, field in extracted.items():
            fields.setdefault(field_name, field)

    warnings = list(raw.warnings)
    if not fields:
        warnings.append(
            "No supported context-labelled institutional fields were extracted; "
            "check the scan and review it manually."
        )
    warnings.append("OCR is advisory only; verify every extracted value against the source.")
    return OCRDocumentResult(
        fields=fields,
        engine=raw.engine,
        engine_version=raw.engine_version,
        source_sha256=hashlib.sha256(image_bytes).hexdigest(),
        warnings=tuple(warnings),
        requires_human_review=True,
    )

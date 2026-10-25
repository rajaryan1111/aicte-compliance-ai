"""Optional OCR pipeline for institutional compliance documents.

This application-owned module does not import the fake-id-screening repository.
OCR output is evidence for human review, never proof of authenticity/compliance.
Install backend/requirements-ocr.txt and the Tesseract system binary to use the
optional Tesseract adapter.

Engine responses are untrusted. The adapter requires the ``text`` and ``conf``
columns (equal-length sequences), optionally accepts aligned ``page_num`` /
``line_num`` metadata, and raises ``RuntimeError`` for structural violations
instead of returning a success-shaped partial result. Individual words whose
confidence is not a finite 0-100 Tesseract percentage are dropped, never
clamped. See ``_validated_engine_columns`` and ``_parse_engine_confidence``.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import math
import re
from collections.abc import Mapping, Sequence
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
    """One engine word. Invalid engine output is rejected, never re-scaled."""

    text: str
    confidence: float
    page_number: int = 1
    line_number: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("OCR word text must be a string")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ):
            raise TypeError("OCR word confidence must be a finite number in [0.0, 1.0]")
        if not math.isfinite(float(self.confidence)):
            raise ValueError("OCR word confidence must be a finite number in [0.0, 1.0]")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("OCR word confidence must be between 0.0 and 1.0")
        for name, value in (
            ("page_number", self.page_number),
            ("line_number", self.line_number),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive 1-based integer")


@dataclass(frozen=True)
class OCRRawResult:
    words: tuple[OCRWord, ...]
    engine: str
    engine_version: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.engine, str) or not self.engine.strip():
            raise ValueError("OCR engine must return a non-empty name.")
        if self.engine_version is not None and not isinstance(self.engine_version, str):
            raise TypeError("engine_version must be a string or None")
        object.__setattr__(self, "words", tuple(self.words))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        for word in self.words:
            if not isinstance(word, OCRWord):
                raise TypeError("OCR result words must be OCRWord instances")
        for warning in self.warnings:
            if not isinstance(warning, str):
                raise TypeError("OCR warnings must be strings")


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


def _validate_confidence(confidence: float | None) -> float | None:
    """Accept only a finite 0.0-1.0 confidence; never clamp silently."""
    if confidence is None:
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise TypeError("confidence must be a finite number between 0.0 and 1.0")
    value = float(confidence)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be a finite number between 0.0 and 1.0")
    return value


def _normalised_confidence(words: tuple[OCRWord, ...]) -> float | None:
    if not words:
        return None
    return sum(word.confidence for word in words) / len(words)


def _date_consistency_warnings(fields: dict[str, OCRField]) -> list[str]:
    """Flag cross-field date contradictions instead of guessing which is right."""
    issue_field = fields.get("issue_date")
    valid_field = fields.get("valid_until")
    if not issue_field or not valid_field:
        return []
    issue_date = parse_iso_date_candidate(issue_field.value)
    valid_date = parse_iso_date_candidate(valid_field.value)
    if issue_date and valid_date and valid_date < issue_date:
        return [
            "Issue date is later than the valid-until date; treat both values as "
            "unresolved and check the source document."
        ]
    return []


_ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\u2060\ufeff"


def _clean_ocr_text(text: str) -> str:
    return text.translate(str.maketrans("", "", _ZERO_WIDTH_CHARS))


_LABEL_TO_FIELD: dict[str, str] = {
    "institution name": "institution_name",
    "name of institution": "institution_name",
    "name of college": "institution_name",
    "college name": "institution_name",
    "संस्थान का नाम": "institution_name",
    "संस्था का नाम": "institution_name",
    "महाविद्यालय का नाम": "institution_name",
    "कॉलेज का नाम": "institution_name",
    "certificate no": "certificate_number",
    "certificate number": "certificate_number",
    "reference no": "certificate_number",
    "reference number": "certificate_number",
    "document no": "certificate_number",
    "प्रमाणपत्र संख्या": "certificate_number",
    "प्रमाणपत्र क्रमांक": "certificate_number",
    "संदर्भ संख्या": "certificate_number",
    "दस्तावेज़ संख्या": "certificate_number",
    "application ref": "application_reference",
    "application reference": "application_reference",
    "application id": "application_reference",
    "application no": "application_reference",
    "आवेदन संदर्भ": "application_reference",
    "आवेदन संख्या": "application_reference",
    "आवेदन क्रमांक": "application_reference",
    "date of issue": "issue_date",
    "issued on": "issue_date",
    "issue date": "issue_date",
    "जारी करने की तिथि": "issue_date",
    "जारी दिनांक": "issue_date",
    "निर्गमन तिथि": "issue_date",
    "valid until": "valid_until",
    "valid up to": "valid_until",
    "valid upto": "valid_until",
    "valid till": "valid_until",
    "expiry date": "valid_until",
    "expires on": "valid_until",
    "वैधता तक": "valid_until",
    "समाप्ति तिथि": "valid_until",
    "अंतिम वैधता तिथि": "valid_until",
    "academic year": "academic_year",
    "academic session": "academic_year",
    "शैक्षणिक वर्ष": "academic_year",
    "शैक्षिक वर्ष": "academic_year",
    "शैक्षणिक सत्र": "academic_year",
    "शैक्षिक सत्र": "academic_year",
}


def _normalize_label(value: str) -> str:
    value = value.translate(str.maketrans("", "", _ZERO_WIDTH_CHARS))
    value = re.sub(r"\s+", " ", value).strip().lower()
    value = value.replace("0", "o").replace("1", "l")
    value = value.replace("lssue", "issue").replace("untill", "until")
    value = value.strip(" :;.-")
    return value


def _field_for_label_text(label_text: str) -> str | None:
    """Map one candidate label string to a field name, or None.

    Exact (normalised) vocabulary matches win; a conservative difflib
    close-match is consulted only when no exact label matches.  Both are
    applied to the whole candidate string only — callers strip the value
    side away first.
    """
    normalized = _normalize_label(label_text)
    if not normalized:
        return None
    if normalized in _LABEL_TO_FIELD:
        return _LABEL_TO_FIELD[normalized]
    matches = difflib.get_close_matches(
        normalized, list(_LABEL_TO_FIELD.keys()), n=1, cutoff=0.86
    )
    if matches:
        return _LABEL_TO_FIELD[matches[0]]
    return None


def _match_label_at_end(region: str) -> tuple[str, int] | None:
    """Find a field label ending at *region*'s end.

    Returns ``(field_name, char_offset)`` where ``char_offset`` is the index
    in ``region`` at which the recognised label begins, or ``None``.  The
    scan tries every suffix word boundary, preferring the longest label
    (earliest start) that matches, so a value tail such as
    ``CERT/2026/0099 Institution Name`` resolves to the trailing
    ``Institution Name`` label and reports where it starts.
    """
    stripped = region.rstrip()
    if not stripped:
        return None
    words = list(re.finditer(r"\S+", stripped))
    for start_idx in range(len(words)):
        candidate = stripped[words[start_idx].start() :]
        if _field_for_label_text(candidate) is not None:
            return _field_for_label_text(candidate), words[start_idx].start()
    return None


def _parse_field_value(field_name: str, raw_value: str) -> str | None:
    raw_value = re.sub(r"\s+", " ", raw_value).strip()
    if not raw_value:
        return None
    if field_name == "institution_name":
        if len(raw_value) < 3 or len(raw_value) > 160:
            return None
        return raw_value
    if field_name in {"certificate_number", "application_reference"}:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/._-]{1,79}", raw_value):
            return None
        return raw_value
    if field_name in {"issue_date", "valid_until"}:
        parsed = parse_iso_date_candidate(raw_value)
        return parsed.isoformat() if parsed is not None else None
    if field_name == "academic_year":
        normalized = re.sub(r"\s+", "", raw_value).replace("/", "-")
        if not re.fullmatch(r"20\d{2}-20\d{2}", normalized):
            return None
        start_text, end_text = normalized.split("-")
        start_year, end_year = int(start_text), int(end_text)
        if end_year != start_year + 1:
            return None
        return normalized
    return raw_value


_SEPARATOR_RE = re.compile(r"[:;]+|\s-\s")


def _extract_from_segment(
    segment: str,
    *,
    confidence: float | None,
    page_number: int,
    fields: dict[str, OCRField],
) -> None:
    """Extract labelled fields from one blank-line-delimited segment.

    The scan finds every ``:``/``;``/`` - `` separator, resolves the label
    text immediately before it, and lets each value run until the next
    *recognised* label starts (not merely until the next separator, which a
    value such as ``2026 - 2027`` can legitimately contain).  Label
    fragments split across whitespace (including across a line break) are
    re-joined because the segment text is space-joined first.
    """
    positions = [m for m in _SEPARATOR_RE.finditer(segment)]
    resolved: list[tuple[str, int, int, int]] = []  # field, label_start, value_start, sep_end
    for match in positions:
        region = segment[: match.start()]
        # Bound the region by the end of the previous resolved value so a
        # previous value's words are not swallowed into this label.
        if resolved:
            region = region[resolved[-1][2] :]
            offset_base = resolved[-1][2]
        else:
            offset_base = 0
        label = _match_label_at_end(region)
        if label is None:
            continue
        field_name, label_offset = label
        label_start = offset_base + label_offset
        resolved.append((field_name, label_start, match.end(), match.end()))

    for idx, (field_name, label_start, value_start, _sep_end) in enumerate(resolved):
        if field_name in fields:
            continue  # first duplicate label wins, deterministically
        if idx + 1 < len(resolved):
            value_end = resolved[idx + 1][1]
        else:
            value_end = len(segment)
        raw_value = segment[value_start:value_end]
        parsed = _parse_field_value(field_name, raw_value)
        if parsed is None:
            continue
        evidence = re.sub(r"\s+", " ", segment[label_start:value_end]).strip()[:500]
        fields[field_name] = OCRField(
            value=parsed,
            confidence=confidence,
            page_number=page_number,
            evidence_text=evidence,
        )


def _extract_column_rows(
    raw_lines: list[str],
    *,
    confidence: float | None,
    page_number: int,
    fields: dict[str, OCRField],
) -> list[str]:
    """Pair a multi-label header row with a value row of the same width.

    OCR that flattens two-column layouts produces a header line with several
    labels separated by runs of spaces, followed by a value line with the
    same number of columns.  Such lines are consumed here (returned list
    omits them) so the separator scan cannot mis-associate the values.  Any
    row that is not a pure label header, or whose value row has a different
    column count, is left untouched.
    """
    remaining: list[str] = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        chunks = [chunk.strip() for chunk in re.split(r"\s{2,}", line) if chunk.strip()]
        if (
            len(chunks) >= 2
            and i + 1 < len(raw_lines)
            and all(_match_label_at_end(chunk) for chunk in chunks)
        ):
            mapped = [_match_label_at_end(chunk) for chunk in chunks]
            field_names = [item[0] for item in mapped if item is not None]
            value_chunks = [
                chunk.strip()
                for chunk in re.split(r"\s{2,}", raw_lines[i + 1])
                if chunk.strip()
            ]
            if len(set(field_names)) == len(chunks) and len(value_chunks) == len(chunks):
                for field_name, raw_value in zip(field_names, value_chunks):
                    if field_name in fields:
                        continue
                    parsed = _parse_field_value(field_name, raw_value)
                    if parsed is not None:
                        fields[field_name] = OCRField(
                            value=parsed,
                            confidence=confidence,
                            page_number=page_number,
                            evidence_text=re.sub(r"\s+", " ", line).strip()[:500],
                        )
                i += 2
                continue
        remaining.append(line)
        i += 1
    return remaining


def extract_institution_fields(
    text: str,
    confidence: float | None = None,
    page_number: int = 1,
) -> dict[str, OCRField]:
    """Extract context-labelled institution fields in English or Hindi.

    Dates are accepted only in strict ISO YYYY-MM-DD form. Ambiguous dates are
    left unresolved rather than guessing day/month order. Personal identity
    fields are deliberately outside this extractor's scope. Inputs over
    ``MAX_OCR_TEXT_CHARS`` and non-finite confidences raise instead of being
    truncated or rescaled, so a caller cannot silently inflate a score.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if len(text) > MAX_OCR_TEXT_CHARS:
        raise ValueError(
            f"OCR text exceeds the {MAX_OCR_TEXT_CHARS}-character processing limit"
        )
    if not text.strip():
        return {}
    if (
        isinstance(page_number, bool)
        or not isinstance(page_number, int)
        or page_number < 1
    ):
        raise ValueError("page_number must be a positive 1-based integer")
    confidence = _validate_confidence(confidence)
    text = _clean_ocr_text(text)
    fields: dict[str, OCRField] = {}

    raw_lines = [line.rstrip() for line in text.splitlines()]
    remaining_lines = _extract_column_rows(
        raw_lines, confidence=confidence, page_number=page_number, fields=fields
    )

    # Blank lines are hard field boundaries: a label and its value may be
    # split across a wrapped line, but never across a blank line.
    segments = re.split(r"\n\s*\n", "\n".join(remaining_lines))
    for segment in segments:
        collapsed = " ".join(
            re.sub(r"\s+", " ", line).strip()
            for line in segment.splitlines()
            if line.strip()
        )
        if not collapsed:
            continue
        _extract_from_segment(
            collapsed, confidence=confidence, page_number=page_number, fields=fields
        )

    return fields


REQUIRED_ENGINE_COLUMNS = ("text", "conf")
OPTIONAL_ENGINE_COLUMNS = ("page_num", "line_num")
MAX_ENGINE_CONFIDENCE_PERCENT = 100.0


def _engine_error(message: str = "no result was produced") -> RuntimeError:
    return RuntimeError(f"Tesseract OCR returned malformed data; {message}.")


def _require_sequence(data: Mapping, key: str, *, required: bool) -> Sequence | None:
    if key not in data:
        if required:
            raise _engine_error(f"required column '{key}' is missing")
        return None
    value = data[key]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _engine_error(f"column '{key}' is not a sequence")
    return value


def _validated_engine_columns(data: object) -> dict[str, Sequence]:
    """Validate the engine's column mapping before indexing it.

    Contract for the Tesseract ``Output.DICT`` mapping (treat as untrusted):

    * **Required:** ``text`` and ``conf``. Both must be present, be sequences
      (not strings/bytes), and have the same length. A missing required column,
      or mismatched required lengths, is malformed output and raises
      ``RuntimeError`` — mismatches are never silently truncated by ``zip``.
    * **Optional:** ``page_num`` and ``line_num``. They may be absent entirely,
      in which case every word defaults to page 1 / line 1. If present they must
      be sequences and must line up with ``text``; a partial metadata column
      would misattribute page/line provenance, so it raises instead of being
      defaulted or truncated.

    A structurally valid empty result (present required columns with zero
    entries) is legitimate and returns empty columns; it is distinguishable from
    malformed output because malformed output raises.
    """
    if not isinstance(data, Mapping):
        raise _engine_error("engine response is not a column mapping")

    columns: dict[str, Sequence] = {}
    for key in REQUIRED_ENGINE_COLUMNS:
        columns[key] = _require_sequence(data, key, required=True)  # type: ignore[assignment]
    for key in OPTIONAL_ENGINE_COLUMNS:
        optional = _require_sequence(data, key, required=False)
        if optional is not None:
            columns[key] = optional

    text_length = len(columns["text"])
    if len(columns["conf"]) != text_length:
        raise _engine_error(
            "required columns 'text' and 'conf' have different lengths"
        )
    for key in OPTIONAL_ENGINE_COLUMNS:
        if key in columns and len(columns[key]) != text_length:
            raise _engine_error(f"column '{key}' does not align with 'text'")
    return columns


def _parse_engine_confidence(value: object) -> float | None:
    """Convert a Tesseract 0-100 percentage to 0.0-1.0; None if unusable.

    The adapter never clamps or inflates: a value above 100, a negative value,
    NaN/infinity, a boolean or a non-numeric value is discarded with its word
    entry so a malformed engine score cannot be presented as high confidence.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(percent):
        return None
    if not 0.0 <= percent <= MAX_ENGINE_CONFIDENCE_PERCENT:
        return None
    return percent / MAX_ENGINE_CONFIDENCE_PERCENT


def _metadata_at(values: Sequence | None, index: int) -> int:
    """Return 1-based page/line metadata, defaulting to 1 when unusable."""
    if values is None:
        return 1
    try:
        return max(1, int(values[index]))
    except (TypeError, ValueError, OverflowError, IndexError):
        return 1


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

        frame_count = 1
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source.load()
                frame_count = max(1, int(getattr(source, "n_frames", 1)))
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
        except Exception as exc:
            # The byte-level check above is structural only; a full decode failure
            # is invalid input, not an engine failure.
            raise OCRInputError("Image could not be decoded safely.") from exc

        try:
            data = pytesseract.image_to_data(
                image, lang=self.language, config="--psm 6", output_type=Output.DICT
            )
        except Exception as exc:
            raise RuntimeError("Tesseract OCR failed; no result was produced.") from exc

        columns = _validated_engine_columns(data)
        page_values = columns.get("page_num")
        line_values = columns.get("line_num")
        words: list[OCRWord] = []
        for index, (raw_text, raw_conf) in enumerate(
            zip(columns["text"], columns["conf"], strict=True)
        ):
            # Non-string text is a schema violation, never stringified into
            # plausible-looking text such as "None" or "123".
            if not isinstance(raw_text, str):
                raise _engine_error(
                    f"column 'text' contains a non-string value at index {index}"
                )
            word = raw_text.strip()
            if not word:
                continue
            confidence = _parse_engine_confidence(raw_conf)
            if confidence is None:
                continue
            words.append(
                OCRWord(
                    text=word,
                    confidence=confidence,
                    page_number=_metadata_at(page_values, index),
                    line_number=_metadata_at(line_values, index),
                )
            )

        warnings: list[str] = []
        if frame_count > 1:
            warnings.append(
                f"Image contains {frame_count} frames/pages; only the first frame "
                "was processed. Submit pages separately for complete coverage."
            )
        try:
            version = str(pytesseract.get_tesseract_version()).splitlines()[0]
        except Exception:
            version = None
        return OCRRawResult(tuple(words), "tesseract", version, tuple(warnings))


def process_institution_document(
    image_bytes: bytes,
    engine: RawOCREngine,
) -> OCRDocumentResult:
    """Validate, OCR and extract institution-document fields for human review."""
    _validate_image_bytes(image_bytes)
    raw = engine.recognize(image_bytes)
    if not isinstance(raw, OCRRawResult):
        raise TypeError("OCR engine must return an OCRRawResult")
    if not raw.engine.strip():
        raise ValueError("OCR engine must return a non-empty name.")

    total_text_chars = sum(len(word.text) + 1 for word in raw.words)
    if total_text_chars > MAX_OCR_TEXT_CHARS:
        raise ValueError(
            f"OCR output exceeds the {MAX_OCR_TEXT_CHARS}-character processing limit"
        )

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
    warnings.extend(_date_consistency_warnings(fields))
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

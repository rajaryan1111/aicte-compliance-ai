"""Raster image OCR benchmark and evaluation module (workstream C / ``ai/``).

Provides:
  - Deterministic synthetic document image generation (English, Hindi, bilingual,
    single-column, two-column table layouts) using Pillow.
  - Genuine raster pixel transformations with reproducible seeds:
    Gaussian blur, horizontal affine skew, low resolution (downsample/upsample),
    JPEG compression artifacts, low contrast, pixel noise, and 90-degree rotation.
  - Ground-truth linking for both transcription text and structured fields.
  - Clean vs. corrupted paired evaluation.
  - Real Tesseract engine adapter integration (with explicit availability detection
    and refusal to fake results when the binary is absent).
  - Deterministic mock engine for testing framework calibration and evaluation math.
  - Quantitative metrics: CER, WER, exact transcription rate, per-field and
    micro-averaged precision, recall, and F1.
  - Granular breakdown by corruption type, language, and layout.

Invariants:
  - All corruptions modify actual image pixels.
  - No real institutional or personal data is used.
  - If Tesseract is not installed on the host system, the prerequisite is explicitly
    reported and never faked or silenced.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import random
import shutil
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Language mapping: dataset language code → Tesseract language code
# ---------------------------------------------------------------------------

#: Dataset language → Tesseract language spec.
#:
#: ``hi`` documents are rendered with Hindi labels *and* Latin values
#: (certificate numbers, institution names, ISO dates), so the Hindi pack alone
#: destroys the Latin tokens: measured on the clean Hindi certificate,
#: ``hin`` gives CER 0.220 against ``hin+eng`` CER 0.115. Both packs are
#: therefore required for a fair Hindi measurement.
DATASET_LANG_TO_TESSERACT: dict[str, str] = {
    "en": "eng",
    "hi": "hin+eng",
    "bilingual": "eng+hin",
}

# ---------------------------------------------------------------------------
# Font selection, script coverage and graceful fallback
# ---------------------------------------------------------------------------

#: Languages whose rendered documents require Devanagari glyph coverage.
DEVANAGARI_LANGUAGES: frozenset[str] = frozenset({"hi", "bilingual"})

#: Environment variable pointing at a Devanagari-capable font file. Used to make
#: real-engine Hindi evaluation reproducible on hosts without a system font.
DEVANAGARI_FONT_ENV = "AICTE_DEVANAGARI_FONT"

#: Latin-script fonts, in preference order.
_LATIN_FONT_CANDIDATES: list[str] = [
    # macOS system / supplemental fonts
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    "/System/Library/Fonts/Geneva.ttf",
    # Linux font paths
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

#: Fonts known to carry Devanagari glyph coverage, in preference order.
_DEVANAGARI_FONT_CANDIDATES: list[str] = [
    # macOS system / supplemental fonts
    "/System/Library/Fonts/Supplemental/DevanagariMT.ttc",
    "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    # Linux font paths
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari[wdth,wght].ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/Gargi/Gargi.ttf",
    "/usr/share/fonts/truetype/samyak/Samyak-Devanagari.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    # Windows
    "C:/Windows/Fonts/mangal.ttf",
    "C:/Windows/Fonts/Nirmala.ttf",
]

#: Directories scanned for a file whose name mentions Devanagari.
_FONT_SEARCH_DIRS: tuple[str, ...] = (
    "~/.fonts",
    "~/.local/share/fonts",
    "/usr/local/share/fonts",
)

#: Kept for backwards compatibility with earlier imports of this module.
_SYSTEM_FONT_CANDIDATES: list[str] = _DEVANAGARI_FONT_CANDIDATES + _LATIN_FONT_CANDIDATES


def _iter_font_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.rglob("*")
        if p.suffix.lower() in {".ttf", ".ttc", ".otf"} and p.is_file()
    )


def resolve_render_font(language: str = "en") -> Optional[str]:
    """Return the font file used to render *language*, or ``None`` if none applies.

    Latin-script documents fall back to Pillow's built-in font, so ``None`` is
    normal there. For Devanagari languages ``None`` means the rendered image
    would contain replacement boxes instead of the labelled text — callers must
    treat that as "cannot measure", never as an OCR result.
    """
    if language in DEVANAGARI_LANGUAGES:
        override = os.environ.get(DEVANAGARI_FONT_ENV)
        if override and os.path.isfile(override):
            return override
        for path in _DEVANAGARI_FONT_CANDIDATES:
            if os.path.isfile(path):
                return path
        for directory in _FONT_SEARCH_DIRS:
            for candidate in _iter_font_files(Path(os.path.expanduser(directory))):
                if "devanagari" in candidate.name.lower():
                    return str(candidate)
        return None

    for path in _LATIN_FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def script_is_renderable(language: str = "en") -> bool:
    """True when the document for *language* can be rendered with real glyphs."""
    if language in DEVANAGARI_LANGUAGES:
        return resolve_render_font(language) is not None
    return True


def _get_font(size: int = 20, language: str = "en") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return a usable FreeType font or fallback to Pillow default.

    A Devanagari-capable font is required for ``hi``/``bilingual`` documents;
    when none is installed the Latin font (or Pillow's bitmap font) is returned
    so that rendering still succeeds, and ``script_is_renderable`` reports the
    loss of script coverage to the caller.
    """
    preferred: list[str] = []
    if language in DEVANAGARI_LANGUAGES:
        resolved = resolve_render_font(language)
        if resolved:
            preferred.append(resolved)
    preferred.extend(_LATIN_FONT_CANDIDATES)

    for path in preferred:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Levenshtein Edit Distance Helpers
# ---------------------------------------------------------------------------


def _levenshtein(seq_a: list | str, seq_b: list | str) -> int:
    """Compute Levenshtein distance between two sequences (characters or tokens)."""
    m, n = len(seq_a), len(seq_b)
    if m > n:
        seq_a, seq_b = seq_b, seq_a
        m, n = n, m

    previous_row = list(range(n + 1))
    for i in range(1, m + 1):
        current_row = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if seq_a[i - 1] == seq_b[j - 1] else 1
            current_row[j] = min(
                current_row[j - 1] + 1,
                previous_row[j] + 1,
                previous_row[j - 1] + cost,
            )
        previous_row = current_row
    return previous_row[n]


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein CER divided by reference length."""
    if not reference and not hypothesis:
        return 0.0
    if not reference or not hypothesis:
        return 1.0
    return _levenshtein(reference, hypothesis) / len(reference)


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Token-level Levenshtein WER divided by reference token count."""
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words and not hyp_words:
        return 0.0
    if not ref_words or not hyp_words:
        return 1.0
    return _levenshtein(ref_words, hyp_words) / len(ref_words)


# ---------------------------------------------------------------------------
# Genuine Pixel-Level Image Transformations
# ---------------------------------------------------------------------------


def apply_gaussian_blur(image: Image.Image, radius: float = 2.0) -> Image.Image:
    """Apply true Gaussian blur to raster pixels."""
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_skew(image: Image.Image, angle_degrees: float = 3.0) -> Image.Image:
    """Apply affine shear (skew) to raster pixels on a white canvas."""
    tan_theta = math.tan(math.radians(angle_degrees))
    # Transform matrix: (a, b, c, d, e, f) mapping x' = x + y*tan, y' = y
    matrix = (1, -tan_theta, 0, 0, 1, 0)
    return image.transform(image.size, Image.Transform.AFFINE, matrix, fillcolor="white")


def apply_low_resolution(image: Image.Image, scale_factor: float = 0.35) -> Image.Image:
    """Simulate low-DPI scan degradation by downsampling and upsampling."""
    scale = max(0.1, min(0.9, scale_factor))
    low_w = max(10, int(image.width * scale))
    low_h = max(10, int(image.height * scale))
    downsampled = image.resize((low_w, low_h), Image.Resampling.BILINEAR)
    return downsampled.resize(image.size, Image.Resampling.NEAREST)


def apply_jpeg_compression(image: Image.Image, quality: int = 15) -> Image.Image:
    """Introduce real 8x8 block discrete cosine transform JPEG compression artifacts."""
    q = max(1, min(95, quality))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=q)
    buffer.seek(0)
    return Image.open(buffer).copy()


def apply_low_contrast(image: Image.Image, factor: float = 0.25) -> Image.Image:
    """Reduce image contrast to simulate faded or poorly lit scans."""
    return ImageEnhance.Contrast(image).enhance(factor)


def apply_noise(image: Image.Image, intensity: float = 0.04, seed: Optional[int] = None) -> Image.Image:
    """Inject salt-and-pepper / scanner sensor noise directly into pixels."""
    rng = random.Random(seed)
    img_rgb = image.convert("RGB")
    pixels = bytearray(img_rgb.tobytes())
    p_len = len(pixels)

    for i in range(0, p_len, 3):
        if rng.random() < intensity:
            val = 255 if rng.random() > 0.5 else 0
            pixels[i] = val
            pixels[i + 1] = val
            pixels[i + 2] = val

    return Image.frombytes("RGB", img_rgb.size, bytes(pixels))


def apply_rotation(image: Image.Image, degrees: int = 90) -> Image.Image:
    """Rotate image by 90/180/270 degrees to simulate document orientation error."""
    return image.rotate(degrees, expand=True, fillcolor="white")


SUPPORTED_IMAGE_CORRUPTIONS: dict[str, Callable[..., Image.Image]] = {
    "none": lambda img, **kw: img.copy(),
    "gaussian_blur": lambda img, **kw: apply_gaussian_blur(img, radius=kw.get("radius", 2.0)),
    "skew": lambda img, **kw: apply_skew(img, angle_degrees=kw.get("angle_degrees", 3.0)),
    "low_resolution": lambda img, **kw: apply_low_resolution(img, scale_factor=kw.get("scale_factor", 0.35)),
    "jpeg_compression": lambda img, **kw: apply_jpeg_compression(img, quality=kw.get("quality", 15)),
    "low_contrast": lambda img, **kw: apply_low_contrast(img, factor=kw.get("factor", 0.25)),
    "noise": lambda img, **kw: apply_noise(img, intensity=kw.get("intensity", 0.04), seed=kw.get("seed")),
    "rotation": lambda img, **kw: apply_rotation(img, degrees=kw.get("degrees", 90)),
}


def apply_raster_corruption(
    image: Image.Image,
    corruption_type: str,
    params: Optional[dict[str, Any]] = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """Apply a named corruption to an image and return (corrupted_image, metadata)."""
    p = dict(params or {})
    func = SUPPORTED_IMAGE_CORRUPTIONS.get(corruption_type)
    if func is None:
        raise ValueError(f"Unsupported corruption type: {corruption_type}")

    corrupted = func(image, **p)
    return corrupted, {"corruption_type": corruption_type, "params": p}


# ---------------------------------------------------------------------------
# Synthetic Document Image Generator
# ---------------------------------------------------------------------------


class RasterDocumentGenerator:
    """Generates synthetic certificate and approval document images."""

    INSTITUTION_NAMES: tuple[str, ...] = (
        "Alpha Institute of Technology",
        "Beta Engineering College",
        "National Technical Academy",
        "Apex Polytechnic Institute",
    )
    CERT_PREFIX: str = "CERT/2026/"
    ACADEMIC_YEARS: tuple[str, ...] = ("2026-2027", "2025-2026")
    VALID_UNTIL_DATES: tuple[str, ...] = ("2027-04-30", "2028-06-30")
    ISSUE_DATES: tuple[str, ...] = ("2026-04-15", "2025-05-20")

    @classmethod
    def generate_document(
        cls,
        *,
        case_idx: int = 0,
        language: str = "en",
        layout: str = "certificate",
        seed: Optional[int] = None,
    ) -> dict[str, Any]:
        """Generate a pristine document image and its exact ground-truth values."""
        rng = random.Random(seed if seed is not None else case_idx)
        inst = cls.INSTITUTION_NAMES[rng.randint(0, len(cls.INSTITUTION_NAMES) - 1)]
        cert = f"{cls.CERT_PREFIX}{case_idx + 1:04d}"
        ay = cls.ACADEMIC_YEARS[rng.randint(0, len(cls.ACADEMIC_YEARS) - 1)]
        vu = cls.VALID_UNTIL_DATES[rng.randint(0, len(cls.VALID_UNTIL_DATES) - 1)]
        idate = cls.ISSUE_DATES[rng.randint(0, len(cls.ISSUE_DATES) - 1)]

        ground_truth = {
            "institution_name": inst,
            "certificate_number": cert,
            "valid_until": vu,
            "academic_year": ay,
            "issue_date": idate,
        }

        # Render image
        width, height = 1200, 600
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)

        font_header = _get_font(26, language=language)
        font_body = _get_font(20, language=language)
        render_font = resolve_render_font(language)
        renderable = script_is_renderable(language)

        lines: list[str] = []

        if layout == "certificate":
            # Outer border
            draw.rectangle([(20, 20), (width - 20, height - 20)], outline="#222222", width=3)
            draw.rectangle([(26, 26), (width - 26, height - 26)], outline="#888888", width=1)

            if language == "hi":
                title = "अखिल भारतीय तकनीकी शिक्षा परिषद - अनुमोदन विस्तार"
                lines.append(title)
                lines.append(f"शैक्षणिक सत्र: {ay}")
                lines.append(f"प्रमाणपत्र संख्या: {cert}")
                lines.append(f"संस्थान: {inst}")
                lines.append(f"मान्यता तक: {vu}")
                lines.append(f"जारी करने की तिथि: {idate}")
            elif language == "bilingual":
                title = "AICTE APPROVAL / अनुमोदन प्रमाणपत्र"
                lines.append(title)
                lines.append(f"Institution / संस्थान: {inst}")
                lines.append(f"Certificate No / प्रमाणपत्र संख्या: {cert}")
                lines.append(f"Academic Year / शैक्षणिक सत्र: {ay}")
                lines.append(f"Valid Until / मान्यता तक: {vu}")
                lines.append(f"Issue Date / जारी करने की तिथि: {idate}")
            else:
                title = "ALL INDIA COUNCIL FOR TECHNICAL EDUCATION"
                subtitle = "EXTENSION OF APPROVAL NOTIFICATION"
                lines.append(title)
                lines.append(subtitle)
                lines.append(f"Institution Name: {inst}")
                lines.append(f"Certificate Number: {cert}")
                lines.append(f"Academic Year: {ay}")
                lines.append(f"Valid Until: {vu}")
                lines.append(f"Issue Date: {idate}")

            # Draw lines centered or structured
            draw.text((60, 50), lines[0], fill="black", font=font_header)
            y_pos = 120
            for line in lines[1:]:
                draw.text((70, y_pos), line, fill="black", font=font_body)
                y_pos += 45

        elif layout == "two_column":
            draw.rectangle([(20, 20), (width - 20, height - 20)], outline="#333333", width=2)
            # The table layout must honour the requested language: a case labelled
            # ``hi`` that renders English labels would be scored against Hindi OCR
            # output while its ground truth is English, which measures nothing.
            if language == "hi":
                title = "अखिल भारतीय तकनीकी शिक्षा परिषद - सारांश तालिका"
                col1_lines = ["संस्थान", "प्रमाणपत्र संख्या", "शैक्षणिक सत्र", "मान्यता तक", "जारी करने की तिथि"]
            elif language == "bilingual":
                title = "AICTE SUMMARY VERIFICATION TABLE / सारांश तालिका"
                col1_lines = [
                    "Institution / संस्थान",
                    "Certificate No / प्रमाणपत्र संख्या",
                    "Academic Year / शैक्षणिक सत्र",
                    "Valid Until / मान्यता तक",
                    "Issue Date / जारी करने की तिथि",
                ]
            else:
                title = "AICTE SUMMARY VERIFICATION TABLE"
                col1_lines = [
                    "Institution Name",
                    "Certificate No",
                    "Academic Year",
                    "Valid Until",
                    "Issue Date",
                ]
            draw.text((50, 40), title, fill="black", font=font_header)
            lines.append(title)
            # Table grid lines
            draw.line([(50, 90), (width - 50, 90)], fill="black", width=2)
            draw.line([(50, 140), (width - 50, 140)], fill="black", width=1)
            draw.line([(50, 190), (width - 50, 190)], fill="black", width=1)
            draw.line([(50, 240), (width - 50, 240)], fill="black", width=1)
            draw.line([(50, 290), (width - 50, 290)], fill="black", width=1)
            draw.line([(450, 90), (450, 340)], fill="black", width=1)

            col2_lines = [inst, cert, ay, vu, idate]

            y_pos = 105
            for col1, col2 in zip(col1_lines, col2_lines, strict=True):
                draw.text((60, y_pos), col1, fill="black", font=font_body)
                draw.text((470, y_pos), col2, fill="black", font=font_body)
                lines.append(f"{col1}: {col2}")
                y_pos += 50

        transcription_text = "\n".join(lines)
        return {
            "image": image,
            "transcription_ground_truth": transcription_text,
            "ground_truth": ground_truth,
            "language": language,
            "layout": layout,
            "render_font": render_font,
            "script_renderable": renderable,
        }

    @classmethod
    def generate_benchmark_dataset(
        cls,
        count: int = 16,
        *,
        seed: int = 42,
    ) -> list[dict[str, Any]]:
        """Generate a paired clean & corrupted raster image benchmark dataset."""
        rng = random.Random(seed)
        dataset_fp = hashlib.sha256(f"raster:{seed}:{count}".encode()).hexdigest()[:16]

        languages = ["en", "bilingual", "hi"]
        layouts = ["certificate", "two_column"]
        corruption_types = [
            "none",
            "gaussian_blur",
            "skew",
            "low_resolution",
            "jpeg_compression",
            "low_contrast",
            "noise",
            "rotation",
        ]

        cases: list[dict[str, Any]] = []

        for i in range(count):
            lang = languages[i % len(languages)]
            layout = layouts[(i // len(languages)) % len(layouts)]
            corr_type = corruption_types[i % len(corruption_types)]

            doc = cls.generate_document(
                case_idx=i,
                language=lang,
                layout=layout,
                seed=rng.randint(0, 1000000),
            )

            clean_img: Image.Image = doc["image"]

            # Save clean image bytes
            clean_buf = io.BytesIO()
            clean_img.save(clean_buf, format="PNG")
            clean_bytes = clean_buf.getvalue()

            # Apply genuine corruption
            corrupted_img, corr_meta = apply_raster_corruption(
                clean_img,
                corr_type,
                params={"seed": seed + i},
            )

            # Save corrupted image bytes
            corr_buf = io.BytesIO()
            corrupted_img.save(corr_buf, format="PNG")
            corr_bytes = corr_buf.getvalue()

            case_id = hashlib.sha256(f"raster_case:{seed}:{i}".encode()).hexdigest()[:12]

            cases.append(
                {
                    "case_id": case_id,
                    "language": lang,
                    "layout": layout,
                    "corruption_type": corr_type,
                    "corruption_params": corr_meta["params"],
                    "clean_image_bytes": clean_bytes,
                    "corrupted_image_bytes": corr_bytes,
                    "clean_image": clean_img,
                    "corrupted_image": corrupted_img,
                    "ground_truth": doc["ground_truth"],
                    "transcription_ground_truth": doc["transcription_ground_truth"],
                    "render_font": doc.get("render_font"),
                    "script_renderable": doc.get("script_renderable", True),
                    "dataset_fingerprint": dataset_fp,
                }
            )

        return cases


# ---------------------------------------------------------------------------
# OCR Engine Interfaces & Mock Implementations
# ---------------------------------------------------------------------------


class RasterOCREngine(ABC):
    """Abstract interface for raster image OCR engines."""

    engine_name: str = "unknown"
    engine_version: Optional[str] = None

    @abstractmethod
    def extract_from_bytes(self, image_bytes: bytes) -> dict[str, Any]:
        """Process image bytes and return transcription text and structured fields.

        Returns:
            dict with at least:
                "transcription": str
                "fields": dict[str, Any]
                "confidence": float (0.0 to 1.0)
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if required system binaries and libraries are present."""
        raise NotImplementedError


class RealTesseractEngine(RasterOCREngine):
    """Adapter executing real Tesseract OCR via backend.app.ocr_pipeline if available.

    Words are grouped by ``(page_number, line_number)`` so that the multiline
    text passed to ``extract_institution_fields`` preserves the line boundaries
    required by its line-oriented regex patterns.
    """

    engine_name = "tesseract"

    def __init__(self, language: str = "eng", *, override_language: bool = False):
        self.language = language
        self.override_language = override_language
        self._available = shutil.which("tesseract") is not None
        self.engine_version: Optional[str] = None
        self._available_languages: set[str] = set()
        if self._available:
            try:
                import pytesseract

                ver_raw = str(pytesseract.get_tesseract_version())
                self.engine_version = ver_raw.splitlines()[0].strip()
            except Exception:
                pass
            try:
                import pytesseract

                self._available_languages = set(pytesseract.get_languages())
            except Exception:
                pass

    def is_available(self) -> bool:
        return self._available

    def has_language(self, lang_code: str) -> bool:
        """Check if all components of a language spec (e.g. ``eng+hin``) are installed."""
        if not self._available_languages:
            # Cannot verify; assume available when the binary exists.
            return self._available
        for part in lang_code.split("+"):
            if part not in self._available_languages:
                return False
        return True

    def extract_from_bytes(self, image_bytes: bytes, *, language: Optional[str] = None) -> dict[str, Any]:
        if not self.is_available():
            raise RuntimeError(
                "Tesseract executable is not installed on this system. "
                "Install Tesseract 5.x via your OS package manager."
            )
        try:
            from backend.app.ocr_pipeline import TesseractOCRAdapter, extract_institution_fields
        except ImportError as exc:
            raise RuntimeError(f"Failed to import backend OCR adapter: {exc}") from exc

        lang = language or self.language
        adapter = TesseractOCRAdapter(language=lang)
        raw_result = adapter.recognize(image_bytes)

        # Group words by (page, line) to preserve line boundaries required by
        # extract_institution_fields (which uses ^…$ regex patterns per line).
        grouped: dict[tuple[int, int], list[str]] = {}
        for w in raw_result.words:
            key = (w.page_number, w.line_number)
            grouped.setdefault(key, []).append(w.text)

        line_texts: list[str] = []
        for key in sorted(grouped):
            line_texts.append(" ".join(grouped[key]))
        text = "\n".join(line_texts)

        fields = extract_institution_fields(text)
        plain_fields = {k: (v.value if hasattr(v, "value") else v) for k, v in fields.items()}

        avg_conf = (
            sum(w.confidence for w in raw_result.words) / len(raw_result.words)
            if raw_result.words
            else 0.0
        )
        return {
            "transcription": text,
            "fields": plain_fields,
            "confidence": avg_conf,
            "engine": "tesseract",
            "engine_version": self.engine_version,
        }


class MockRasterOCREngine(RasterOCREngine):
    """Calibrated mock engine simulating realistic OCR degradation under corruption.

    Used for automated tests, baseline verification, and framework calibration
    independent of external OS binaries.
    """

    engine_name = "mock_calibrated"
    engine_version = "1.0.0"

    def __init__(self, corruption_error_rates: Optional[dict[str, float]] = None):
        self.corruption_error_rates = corruption_error_rates or {
            "none": 0.0,
            "low_contrast": 0.05,
            "jpeg_compression": 0.10,
            "noise": 0.15,
            "skew": 0.20,
            "low_resolution": 0.40,
            "gaussian_blur": 0.50,
            "rotation": 0.95,
        }

    def is_available(self) -> bool:
        return True

    def extract_from_bytes(
        self,
        image_bytes: bytes,
        *,
        reference_text: str = "",
        reference_fields: Optional[dict[str, Any]] = None,
        corruption_type: str = "none",
    ) -> dict[str, Any]:
        error_rate = self.corruption_error_rates.get(corruption_type, 0.1)

        # Degrade transcription
        if error_rate == 0.0 or not reference_text:
            pred_text = reference_text
        elif error_rate >= 0.9:
            pred_text = ""  # severe rotation/blur yields unreadable text
        else:
            # Introduce character substitutions. The seed is derived from a stable
            # SHA-256 digest of the image bytes (not ``hash()`` or ``len()``) so the
            # degradation is identical in every Python process and is sensitive to
            # the actual pixels rather than the encoded size.
            chars = list(reference_text)
            rng = random.Random(int(hashlib.sha256(image_bytes).hexdigest()[:16], 16))
            for idx in range(len(chars)):
                if rng.random() < error_rate:
                    chars[idx] = "X"
            pred_text = "".join(chars)

        # Degrade structured fields
        pred_fields: dict[str, Any] = {}
        if reference_fields and error_rate < 0.8:
            for k, v in reference_fields.items():
                # Use hashlib for cross-process determinism (hash() varies per PYTHONHASHSEED).
                stable_seed = int(hashlib.sha256(k.encode()).hexdigest()[:8], 16) + len(image_bytes)
                if random.Random(stable_seed).random() > error_rate:
                    pred_fields[k] = v

        conf = max(0.0, min(1.0, 1.0 - error_rate))
        return {
            "transcription": pred_text,
            "fields": pred_fields,
            "confidence": round(conf, 4),
            "engine": self.engine_name,
        }


# ---------------------------------------------------------------------------
# Engine language resolution
# ---------------------------------------------------------------------------


def tesseract_language_for(engine: "RealTesseractEngine", case_language: str) -> str:
    """Resolve the Tesseract language spec for a case.

    An explicit ``--language``/constructor override wins for every case (useful
    for controlled comparisons); otherwise the dataset language is mapped through
    :data:`DATASET_LANG_TO_TESSERACT`.
    """
    if getattr(engine, "override_language", False) and getattr(engine, "language", None):
        return engine.language
    return DATASET_LANG_TO_TESSERACT.get(case_language, "eng")


# ---------------------------------------------------------------------------
# Quantitative Benchmark Scorer & Comparator
# ---------------------------------------------------------------------------


class RasterBenchmarkScorer:
    """Evaluates transcription and structured field accuracy across clean and corrupted images."""

    @classmethod
    def evaluate_case(
        cls,
        *,
        predicted_text: str,
        expected_text: str,
        predicted_fields: dict[str, Any],
        expected_fields: dict[str, Any],
    ) -> dict[str, Any]:
        cer = character_error_rate(expected_text, predicted_text)
        wer = word_error_rate(expected_text, predicted_text)
        exact_text = 1.0 if expected_text == predicted_text else 0.0

        # Structured fields
        field_keys = set(expected_fields.keys()) | set(predicted_fields.keys())
        tp = 0
        fp = 0
        fn = 0
        for k in field_keys:
            ev = expected_fields.get(k)
            pv = predicted_fields.get(k)
            if ev is None and pv is None:
                continue
            if ev is not None and pv is not None and str(ev) == str(pv):
                tp += 1
            elif ev is not None and pv is not None:
                fp += 1
                fn += 1
            elif pv is not None:
                fp += 1
            else:
                fn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            "cer": round(cer, 4),
            "wer": round(wer, 4),
            "exact_transcription": exact_text,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    @classmethod
    def run_benchmark(
        cls,
        cases: list[dict[str, Any]],
        engine: RasterOCREngine,
    ) -> dict[str, Any]:
        """Run full benchmark evaluating both clean and corrupted pairs.

        For real engines, per-case language selection is performed using
        ``DATASET_LANG_TO_TESSERACT``.  Cases requiring unavailable language
        packs are excluded from scored aggregates and reported separately.
        """
        if not engine.is_available():
            return {
                "available": False,
                "engine": engine.engine_name,
                "engine_type": "real" if isinstance(engine, RealTesseractEngine) else "mock",
                "error": f"Engine {engine.engine_name} is unavailable on this host system.",
                "total_cases": len(cases),
            }

        start_time = time.time()

        clean_results: list[dict[str, Any]] = []
        corrupted_results: list[dict[str, Any]] = []
        per_corruption: dict[str, list[dict[str, Any]]] = {}
        per_language: dict[str, list[dict[str, Any]]] = {}
        clean_per_corruption: dict[str, list[dict[str, Any]]] = {}
        clean_per_language: dict[str, list[dict[str, Any]]] = {}
        case_results: list[dict[str, Any]] = []
        unavailable_cases: list[dict[str, Any]] = []

        for case in cases:
            corr_type = case.get("corruption_type", "none")
            lang = case.get("language", "en")
            exp_text = case.get("transcription_ground_truth", "")
            exp_fields = case.get("ground_truth", {})
            case_id = case.get("case_id", "unknown")

            # --- language availability check for real engines ---------------
            if isinstance(engine, RealTesseractEngine):
                tesseract_lang = tesseract_language_for(engine, lang)
                if not engine.has_language(tesseract_lang):
                    missing = [
                        p
                        for p in tesseract_lang.split("+")
                        if p not in engine._available_languages
                    ]
                    reason = f"Missing Tesseract language pack(s): {', '.join(missing)}"
                    unavailable_cases.append({
                        "case_id": case_id,
                        "language": lang,
                        "tesseract_language": tesseract_lang,
                        "status": "unavailable",
                        "reason": reason,
                    })
                    case_results.append({
                        "case_id": case_id,
                        "language": lang,
                        "layout": case.get("layout", "unknown"),
                        "corruption_type": corr_type,
                        "status": "unavailable",
                        "reason": reason,
                    })
                    continue

                # --- script coverage check ---------------------------------
                # Without a Devanagari-capable font the rendered image contains
                # replacement boxes instead of the labelled Hindi text, so any
                # CER/WER computed from it would measure the renderer, not OCR.
                if lang in DEVANAGARI_LANGUAGES and resolve_render_font(lang) is None:
                    reason = (
                        "No Devanagari-capable font available for rendering: the "
                        "document image does not contain the labelled text "
                        f"(set {DEVANAGARI_FONT_ENV} to a Devanagari font file)"
                    )
                    unavailable_cases.append({
                        "case_id": case_id,
                        "language": lang,
                        "tesseract_language": tesseract_lang,
                        "status": "unavailable",
                        "reason": reason,
                    })
                    case_results.append({
                        "case_id": case_id,
                        "language": lang,
                        "layout": case.get("layout", "unknown"),
                        "corruption_type": corr_type,
                        "status": "unavailable",
                        "reason": reason,
                    })
                    continue

            # --- clean evaluation -------------------------------------------
            try:
                if isinstance(engine, MockRasterOCREngine):
                    res_clean = engine.extract_from_bytes(
                        case["clean_image_bytes"],
                        reference_text=exp_text,
                        reference_fields=exp_fields,
                        corruption_type="none",
                    )
                elif isinstance(engine, RealTesseractEngine):
                    tesseract_lang = tesseract_language_for(engine, lang)
                    res_clean = engine.extract_from_bytes(
                        case["clean_image_bytes"],
                        language=tesseract_lang,
                    )
                else:
                    res_clean = engine.extract_from_bytes(case["clean_image_bytes"])
            except Exception as exc:
                case_results.append({
                    "case_id": case_id,
                    "language": lang,
                    "layout": case.get("layout", "unknown"),
                    "corruption_type": corr_type,
                    "status": "error",
                    "reason": f"Clean evaluation failed: {exc}",
                })
                continue

            eval_clean = cls.evaluate_case(
                predicted_text=res_clean.get("transcription", ""),
                expected_text=exp_text,
                predicted_fields=res_clean.get("fields", {}),
                expected_fields=exp_fields,
            )
            clean_results.append(eval_clean)

            # --- corrupted evaluation --------------------------------------
            try:
                if isinstance(engine, MockRasterOCREngine):
                    res_corr = engine.extract_from_bytes(
                        case["corrupted_image_bytes"],
                        reference_text=exp_text,
                        reference_fields=exp_fields,
                        corruption_type=corr_type,
                    )
                elif isinstance(engine, RealTesseractEngine):
                    tesseract_lang = tesseract_language_for(engine, lang)
                    res_corr = engine.extract_from_bytes(
                        case["corrupted_image_bytes"],
                        language=tesseract_lang,
                    )
                else:
                    res_corr = engine.extract_from_bytes(case["corrupted_image_bytes"])
            except Exception as exc:
                case_results.append({
                    "case_id": case_id,
                    "language": lang,
                    "layout": case.get("layout", "unknown"),
                    "corruption_type": corr_type,
                    "status": "error",
                    "reason": f"Corrupted evaluation failed: {exc}",
                })
                continue

            eval_corr = cls.evaluate_case(
                predicted_text=res_corr.get("transcription", ""),
                expected_text=exp_text,
                predicted_fields=res_corr.get("fields", {}),
                expected_fields=exp_fields,
            )
            corrupted_results.append(eval_corr)

            per_corruption.setdefault(corr_type, []).append(eval_corr)
            per_language.setdefault(lang, []).append(eval_corr)
            clean_per_corruption.setdefault(corr_type, []).append(eval_clean)
            clean_per_language.setdefault(lang, []).append(eval_clean)

            # --- per-case detail -------------------------------------------
            case_results.append({
                "case_id": case_id,
                "language": lang,
                "layout": case.get("layout", "unknown"),
                "corruption_type": corr_type,
                "status": "evaluated",
                "expected_text": exp_text,
                "expected_fields": exp_fields,
                "clean": {
                    "predicted_text": res_clean.get("transcription", ""),
                    "predicted_fields": res_clean.get("fields", {}),
                    **eval_clean,
                },
                "corrupted": {
                    "predicted_text": res_corr.get("transcription", ""),
                    "predicted_fields": res_corr.get("fields", {}),
                    **eval_corr,
                },
            })

        elapsed = time.time() - start_time
        evaluated_count = len(clean_results)
        corrupted_count = len(corrupted_results)

        def _aggregate(res_list: list[dict[str, Any]]) -> dict[str, Any]:
            """Aggregate per-case results.

            When nothing was scored the metrics are ``None`` (JSON ``null``) and
            ``scored_cases`` is 0 - never 0.0, which would read as a perfect score
            for a measurement that did not happen.
            """
            if not res_list:
                return {
                    "scored_cases": 0,
                    "cer": None,
                    "wer": None,
                    "exact": None,
                    "precision": None,
                    "recall": None,
                    "f1": None,
                }
            tot_tp = sum(r["tp"] for r in res_list)
            tot_fp = sum(r["fp"] for r in res_list)
            tot_fn = sum(r["fn"] for r in res_list)
            p = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) > 0 else 0.0
            r = tot_tp / (tot_tp + tot_fn) if (tot_tp + tot_fn) > 0 else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            return {
                "scored_cases": len(res_list),
                "cer": round(sum(r["cer"] for r in res_list) / len(res_list), 4),
                "wer": round(sum(r["wer"] for r in res_list) / len(res_list), 4),
                "exact": round(sum(r["exact_transcription"] for r in res_list) / len(res_list), 4),
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f1, 4),
            }

        def _delta(clean_value: Optional[float], corr_value: Optional[float], *, invert: bool = False) -> Optional[float]:
            if clean_value is None or corr_value is None:
                return None
            value = clean_value - corr_value if invert else corr_value - clean_value
            return round(value, 4)

        clean_agg = _aggregate(clean_results)
        corr_agg = _aggregate(corrupted_results)

        corr_breakdown = {k: _aggregate(v) for k, v in per_corruption.items()}
        lang_breakdown = {k: _aggregate(v) for k, v in per_language.items()}
        clean_corr_breakdown = {k: _aggregate(v) for k, v in clean_per_corruption.items()}
        clean_lang_breakdown = {k: _aggregate(v) for k, v in clean_per_language.items()}

        dataset_fp = cases[0].get("dataset_fingerprint", "unknown") if cases else "unknown"

        render_fonts: dict[str, Optional[str]] = {}
        for evaluated_lang in sorted({r.get("language", "en") for r in case_results if r.get("status") == "evaluated"}):
            render_fonts[evaluated_lang] = resolve_render_font(evaluated_lang)

        report: dict[str, Any] = {
            "available": True,
            "engine": engine.engine_name,
            "engine_version": getattr(engine, "engine_version", None),
            "engine_type": "real" if isinstance(engine, RealTesseractEngine) else "mock",
            "dataset_fingerprint": dataset_fp,
            "total_cases": len(cases),
            "evaluated_count": evaluated_count,
            "corrupted_count": corrupted_count,
            "unavailable_count": len(unavailable_cases),
            "sample_size": evaluated_count,
            "metrics_available": evaluated_count > 0,
            "duration_seconds": round(elapsed, 3),
            "render_fonts": render_fonts,
            "clean_baseline": clean_agg,
            "corrupted_evaluation": corr_agg,
            "degradation_delta": {
                "cer_increase": _delta(clean_agg["cer"], corr_agg["cer"]),
                "wer_increase": _delta(clean_agg["wer"], corr_agg["wer"]),
                "f1_drop": _delta(clean_agg["f1"], corr_agg["f1"], invert=True),
            },
            "by_corruption_type": corr_breakdown,
            "by_language": lang_breakdown,
            "clean_by_corruption_type": clean_corr_breakdown,
            "clean_by_language": clean_lang_breakdown,
            "case_results": case_results,
        }

        if unavailable_cases:
            report["unavailable_cases"] = unavailable_cases

        return report


# ---------------------------------------------------------------------------
# CLI Command
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Raster Image OCR Benchmark")
    parser.add_argument("--count", type=int, default=16, help="Number of synthetic document images to generate")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    parser.add_argument("--json", type=Path, help="Write machine-readable benchmark report to JSON file")
    parser.add_argument("--output-images", type=Path, help="Optional directory to save generated PNG images")
    parser.add_argument("--real-engine", action="store_true", help="Attempt real Tesseract engine evaluation")
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help=(
            "Force this Tesseract language code for every case (e.g. eng, hin, eng+hin). "
            "Omit to map each case's dataset language via DATASET_LANG_TO_TESSERACT."
        ),
    )
    args = parser.parse_args()

    if args.count < 1:
        print("ERROR: --count must be at least 1.", file=sys.stderr)
        return 1

    print("Generating synthetic raster image dataset...")
    cases = RasterDocumentGenerator.generate_benchmark_dataset(count=args.count, seed=args.seed)
    print(f"Generated {len(cases)} paired clean/corrupted test cases.")

    if args.output_images:
        args.output_images.mkdir(parents=True, exist_ok=True)
        for c in cases:
            clean_path = args.output_images / f"{c['case_id']}_clean.png"
            corr_path = args.output_images / f"{c['case_id']}_{c['corruption_type']}.png"
            clean_path.write_bytes(c["clean_image_bytes"])
            corr_path.write_bytes(c["corrupted_image_bytes"])
        print(f"Saved {len(cases) * 2} images to {args.output_images}")

    engine: RasterOCREngine
    if args.real_engine:
        if args.language:
            engine = RealTesseractEngine(language=args.language, override_language=True)
        else:
            engine = RealTesseractEngine()
        if not engine.is_available():
            print("ERROR: Real Tesseract engine requested, but 'tesseract' was not found in PATH.")
            return 1
        print(f"Tesseract version: {engine.engine_version}")
        if engine._available_languages:
            print(f"Available languages: {', '.join(sorted(engine._available_languages))}")
    else:
        engine = MockRasterOCREngine()

    print(f"Running benchmark with engine '{engine.engine_name}'...")
    report = RasterBenchmarkScorer.run_benchmark(cases, engine)

    if not report.get("available"):
        print(f"Engine unavailable: {report.get('error')}")
        return 1

    clean = report["clean_baseline"]
    corr = report["corrupted_evaluation"]
    delta = report["degradation_delta"]

    def _fmt(value: Optional[float]) -> str:
        """Format a metric, printing ``n/a`` when nothing was measured."""
        return "n/a" if value is None else f"{value:.3f}"

    print("\n================ RASTER OCR BENCHMARK REPORT ================")
    print(
        f"Engine: {report['engine']} ({report.get('engine_type', 'unknown')}) | "
        f"Evaluated: {report['evaluated_count']}/{report['total_cases']} | "
        f"Time: {report['duration_seconds']}s"
    )
    if report.get("engine_version"):
        print(f"Engine Version: {report['engine_version']}")
    print("-------------------------------------------------------------")
    print(f"CLEAN:     CER={_fmt(clean['cer'])} | WER={_fmt(clean['wer'])} | Exact={_fmt(clean['exact'])} | F1={_fmt(clean['f1'])}")
    print(f"CORRUPTED: CER={_fmt(corr['cer'])} | WER={_fmt(corr['wer'])} | Exact={_fmt(corr['exact'])} | F1={_fmt(corr['f1'])}")
    print(f"DELTA:     +CER={_fmt(delta['cer_increase'])} | +WER={_fmt(delta['wer_increase'])} | -F1={_fmt(delta['f1_drop'])}")
    if report.get("unavailable_count", 0) > 0:
        print(f"UNAVAILABLE: {report['unavailable_count']} case(s) excluded (not measurable on this host)")
        for uc in report.get("unavailable_cases", []):
            print(f"  {uc['case_id']} ({uc['language']}): {uc['reason']}")
    if report.get("render_fonts"):
        print("Rendered with:")
        for lang, font_path in sorted(report["render_fonts"].items()):
            print(f"  {lang:18s} -> {font_path or 'Pillow default font'}")
    print("-------------------------------------------------------------")
    print("Performance by Corruption Type:")
    for corr_type, stats in sorted(report["by_corruption_type"].items()):
        print(f"  {corr_type:18s} -> CER={_fmt(stats['cer'])} | WER={_fmt(stats['wer'])} | F1={_fmt(stats['f1'])}")
    print("Corrupted performance by Language:")
    for lang, stats in sorted(report["by_language"].items()):
        print(f"  {lang:18s} -> CER={_fmt(stats['cer'])} | WER={_fmt(stats['wer'])} | F1={_fmt(stats['f1'])}")
    print("Clean performance by Language:")
    for lang, stats in sorted(report.get("clean_by_language", {}).items()):
        print(f"  {lang:18s} -> CER={_fmt(stats['cer'])} | WER={_fmt(stats['wer'])} | F1={_fmt(stats['f1'])}")
    print("=============================================================")

    if not report.get("metrics_available"):
        print(
            "ERROR: no case could be scored, so no OCR metric was measured. "
            "This is not a zero-error result.",
            file=sys.stderr,
        )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        report["seed"] = args.seed
        report["count"] = args.count
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to {args.json}")

    return 0 if report.get("metrics_available") else 2


if __name__ == "__main__":
    sys.exit(main())

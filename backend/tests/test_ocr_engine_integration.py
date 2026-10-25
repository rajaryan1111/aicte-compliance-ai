import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from backend.app.ocr_pipeline import TesseractOCRAdapter

# Cross-platform font candidates for the synthetic document. The previous
# hardcoded Linux-only path (/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf)
# made this test fail on any non-Linux host with Tesseract installed
# (documented in ai/BACKEND_HANDOFF.md); probing a small candidate list and
# skipping with a reason keeps the smoke test portable.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _synthetic_document_font(size: int = 58) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    pytest.skip(
        "no supported system TrueType font on this host; the synthetic OCR "
        "document needs one to be rendered legibly"
    )


@pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract is optional; the dedicated OCR CI job installs it.",
)
def test_tesseract_reads_synthetic_institution_document():
    image = Image.new("RGB", (1800, 500), "white")
    draw = ImageDraw.Draw(image)
    font = _synthetic_document_font()
    draw.text((60, 70), "Institution Name: Example Technical Institute", fill="black", font=font)
    draw.text((60, 190), "Certificate No: CERT-2026-0042", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    result = TesseractOCRAdapter(language="eng").recognize(buffer.getvalue())
    recognized = " ".join(word.text for word in result.words).casefold()
    assert result.engine == "tesseract"
    assert result.engine_version
    assert "institution" in recognized
    assert "certificate" in recognized
    assert all(0.0 <= word.confidence <= 1.0 for word in result.words)

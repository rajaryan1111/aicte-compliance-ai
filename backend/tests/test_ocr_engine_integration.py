import io
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from backend.app.ocr_pipeline import TesseractOCRAdapter


@pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract is optional; the dedicated OCR CI job installs it.",
)
def test_tesseract_reads_synthetic_institution_document():
    image = Image.new("RGB", (1800, 500), "white")
    draw = ImageDraw.Draw(image)
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
    ]
    font_path = next(
        (candidate for candidate in font_candidates if Path(candidate).is_file()),
        None,
    )
    font = (
        ImageFont.truetype(font_path, 58)
        if font_path
        else ImageFont.load_default(size=58)
    )
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

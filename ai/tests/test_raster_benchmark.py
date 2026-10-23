"""Tests for the raster image OCR benchmark module (ai/raster_benchmark.py).

Covers:
  - Genuine pixel modification by all supported corruptions.
  - Synthetic document generation across languages and layouts.
  - Traceability and pairing of clean and corrupted images.
  - Transcription and structured-field metrics calculation.
  - Real Tesseract engine availability detection.
  - Mock engine calibration and degradation delta measurement.
  - Machine-readable benchmark report generation and CLI execution.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.raster_benchmark import (  # noqa: E402
    DATASET_LANG_TO_TESSERACT,
    DEVANAGARI_FONT_ENV,
    DEVANAGARI_LANGUAGES,
    MockRasterOCREngine,
    RasterBenchmarkScorer,
    RasterDocumentGenerator,
    RealTesseractEngine,
    SUPPORTED_IMAGE_CORRUPTIONS,
    apply_gaussian_blur,
    apply_jpeg_compression,
    apply_low_contrast,
    apply_low_resolution,
    apply_noise,
    apply_raster_corruption,
    apply_rotation,
    apply_skew,
    character_error_rate,
    resolve_render_font,
    script_is_renderable,
    tesseract_language_for,
    word_error_rate,
)


# ---------------------------------------------------------------------------
# Test Pixel Transformations
# ---------------------------------------------------------------------------


class TestPixelTransformations:
    @classmethod
    def _create_sample_image(cls) -> Image.Image:
        img = Image.new("RGB", (300, 100), "white")
        # Draw some high-contrast black shapes and lines so transforms alter pixels
        for x in range(30, 270, 20):
            for y in range(20, 80):
                img.putpixel((x, y), (0, 0, 0))
        return img

    def test_gaussian_blur_modifies_pixels(self):
        original = self._create_sample_image()
        blurred = apply_gaussian_blur(original, radius=2.0)
        assert blurred.tobytes() != original.tobytes()
        assert blurred.size == original.size

    def test_skew_modifies_pixels(self):
        original = self._create_sample_image()
        skewed = apply_skew(original, angle_degrees=4.0)
        assert skewed.tobytes() != original.tobytes()
        assert skewed.size == original.size

    def test_low_resolution_modifies_pixels(self):
        original = self._create_sample_image()
        low_res = apply_low_resolution(original, scale_factor=0.3)
        assert low_res.tobytes() != original.tobytes()
        assert low_res.size == original.size

    def test_jpeg_compression_modifies_pixels(self):
        original = self._create_sample_image()
        compressed = apply_jpeg_compression(original, quality=10)
        assert compressed.tobytes() != original.tobytes()
        assert compressed.size == original.size

    def test_low_contrast_modifies_pixels(self):
        original = self._create_sample_image()
        faded = apply_low_contrast(original, factor=0.2)
        assert faded.tobytes() != original.tobytes()
        assert faded.size == original.size

    def test_noise_modifies_pixels(self):
        original = self._create_sample_image()
        noisy = apply_noise(original, intensity=0.08, seed=42)
        assert noisy.tobytes() != original.tobytes()
        assert noisy.size == original.size

    def test_noise_is_deterministic_with_seed(self):
        original = self._create_sample_image()
        noisy1 = apply_noise(original, intensity=0.05, seed=99)
        noisy2 = apply_noise(original, intensity=0.05, seed=99)
        assert noisy1.tobytes() == noisy2.tobytes()

    def test_rotation_modifies_pixels_and_dimensions(self):
        original = self._create_sample_image()  # 300 x 100
        rotated = apply_rotation(original, degrees=90)
        assert rotated.tobytes() != original.tobytes()
        # 90-degree expansion swaps width and height
        assert rotated.size == (100, 300)

    def test_all_supported_corruptions_modify_pixels(self):
        original = self._create_sample_image()
        for corr_type in SUPPORTED_IMAGE_CORRUPTIONS:
            if corr_type == "none":
                continue
            corrupted, meta = apply_raster_corruption(original, corr_type, params={"seed": 123})
            assert corrupted.tobytes() != original.tobytes(), f"{corr_type} failed to modify pixels"
            assert meta["corruption_type"] == corr_type


# ---------------------------------------------------------------------------
# Test Document Image Generation
# ---------------------------------------------------------------------------


class TestRasterDocumentGeneration:
    def test_generate_english_certificate(self):
        doc = RasterDocumentGenerator.generate_document(
            case_idx=1, language="en", layout="certificate", seed=42
        )
        assert isinstance(doc["image"], Image.Image)
        assert doc["image"].size == (1200, 600)
        assert "ALL INDIA COUNCIL" in doc["transcription_ground_truth"]
        assert doc["ground_truth"]["certificate_number"] == "CERT/2026/0002"
        assert doc["language"] == "en"

    def test_generate_hindi_certificate(self):
        doc = RasterDocumentGenerator.generate_document(
            case_idx=2, language="hi", layout="certificate", seed=42
        )
        assert isinstance(doc["image"], Image.Image)
        assert "अखिल भारतीय तकनीकी शिक्षा परिषद" in doc["transcription_ground_truth"]
        assert "शैक्षणिक सत्र" in doc["transcription_ground_truth"]
        assert doc["language"] == "hi"

    def test_generate_bilingual_certificate(self):
        doc = RasterDocumentGenerator.generate_document(
            case_idx=3, language="bilingual", layout="certificate", seed=42
        )
        assert "AICTE APPROVAL" in doc["transcription_ground_truth"]
        assert doc["language"] == "bilingual"

    def test_generate_two_column_layout(self):
        doc = RasterDocumentGenerator.generate_document(
            case_idx=4, language="en", layout="two_column", seed=42
        )
        assert "AICTE SUMMARY VERIFICATION TABLE" in doc["transcription_ground_truth"]
        assert "Institution Name:" in doc["transcription_ground_truth"]
        assert doc["layout"] == "two_column"

    def test_two_column_layout_honours_language(self):
        """A ``hi`` table case must render Hindi labels, not the English table."""
        doc_hi = RasterDocumentGenerator.generate_document(
            case_idx=4, language="hi", layout="two_column", seed=42
        )
        text = doc_hi["transcription_ground_truth"]
        assert "Institution Name" not in text
        assert "संस्थान" in text
        assert "प्रमाणपत्र संख्या" in text

        doc_bi = RasterDocumentGenerator.generate_document(
            case_idx=4, language="bilingual", layout="two_column", seed=42
        )
        text_bi = doc_bi["transcription_ground_truth"]
        assert "Institution / संस्थान" in text_bi
        assert "Academic Year / शैक्षणिक सत्र" in text_bi

    def test_deterministic_generation_with_seed(self):
        doc1 = RasterDocumentGenerator.generate_document(case_idx=5, seed=100)
        doc2 = RasterDocumentGenerator.generate_document(case_idx=5, seed=100)
        assert doc1["ground_truth"] == doc2["ground_truth"]
        assert doc1["transcription_ground_truth"] == doc2["transcription_ground_truth"]
        assert doc1["image"].tobytes() == doc2["image"].tobytes()


# ---------------------------------------------------------------------------
# Test Dataset Generation & Traceability
# ---------------------------------------------------------------------------


class TestBenchmarkDataset:
    def test_dataset_generation_count_and_keys(self):
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=8, seed=42)
        assert len(cases) == 8

        required_keys = {
            "case_id",
            "language",
            "layout",
            "corruption_type",
            "corruption_params",
            "clean_image_bytes",
            "corrupted_image_bytes",
            "ground_truth",
            "transcription_ground_truth",
            "dataset_fingerprint",
        }
        for c in cases:
            assert required_keys <= set(c.keys())
            assert isinstance(c["clean_image_bytes"], bytes)
            assert isinstance(c["corrupted_image_bytes"], bytes)
            assert len(c["clean_image_bytes"]) > 0
            assert len(c["corrupted_image_bytes"]) > 0

    def test_clean_vs_corrupted_bytes_differ_for_corruptions(self):
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=16, seed=42)
        corrupted_cases = [c for c in cases if c["corruption_type"] != "none"]
        assert len(corrupted_cases) > 0
        for c in corrupted_cases:
            assert c["clean_image_bytes"] != c["corrupted_image_bytes"]

    def test_dataset_fingerprint_stability(self):
        cases1 = RasterDocumentGenerator.generate_benchmark_dataset(count=6, seed=77)
        cases2 = RasterDocumentGenerator.generate_benchmark_dataset(count=6, seed=77)
        assert cases1[0]["dataset_fingerprint"] == cases2[0]["dataset_fingerprint"]


# ---------------------------------------------------------------------------
# Test Metrics and Scorer
# ---------------------------------------------------------------------------


class TestRasterScorer:
    def test_perfect_transcription_and_fields(self):
        result = RasterBenchmarkScorer.evaluate_case(
            predicted_text="hello world",
            expected_text="hello world",
            predicted_fields={"inst": "Alpha"},
            expected_fields={"inst": "Alpha"},
        )
        assert result["cer"] == 0.0
        assert result["wer"] == 0.0
        assert result["exact_transcription"] == 1.0
        assert result["f1"] == 1.0
        assert result["tp"] == 1
        assert result["fp"] == 0
        assert result["fn"] == 0

    def test_character_and_word_error_rates(self):
        assert character_error_rate("cat", "cut") == 1 / 3
        assert word_error_rate("the cat sat", "the dog sat") == 1 / 3
        assert character_error_rate("", "") == 0.0
        assert character_error_rate("abc", "") == 1.0

    def test_benchmark_run_with_mock_engine(self):
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=8, seed=42)
        engine = MockRasterOCREngine()
        report = RasterBenchmarkScorer.run_benchmark(cases, engine)

        assert report["available"] is True
        assert report["engine"] == "mock_calibrated"
        assert report["sample_size"] == 8

        # Clean baseline should have near-perfect accuracy with mock engine
        clean = report["clean_baseline"]
        assert math.isclose(clean["cer"], 0.0, abs_tol=1e-3)
        assert math.isclose(clean["f1"], 1.0, abs_tol=1e-3)

        # Corrupted evaluation should demonstrate measurable degradation
        corrupted = report["corrupted_evaluation"]
        assert corrupted["cer"] > clean["cer"]
        assert corrupted["f1"] < clean["f1"]

        # Delta must reflect positive degradation
        delta = report["degradation_delta"]
        assert delta["cer_increase"] > 0
        assert delta["f1_drop"] > 0

        # Breakdowns must exist
        assert "by_corruption_type" in report
        assert "by_language" in report

    def test_real_tesseract_engine_availability_check(self):
        engine = RealTesseractEngine()
        # On this system tesseract is not in PATH
        if not engine.is_available():
            cases = RasterDocumentGenerator.generate_benchmark_dataset(count=2, seed=42)
            report = RasterBenchmarkScorer.run_benchmark(cases, engine)
            assert report["available"] is False
            assert "unavailable" in report["error"]


# ---------------------------------------------------------------------------
# Test CLI Functionality
# ---------------------------------------------------------------------------


class TestRasterBenchmarkCLI:
    def test_cli_generates_json_report(self, tmp_path):
        json_out = tmp_path / "report.json"
        img_dir = tmp_path / "images"

        import subprocess

        cmd = [
            sys.executable,
            "ai/raster_benchmark.py",
            "--count",
            "4",
            "--seed",
            "123",
            "--json",
            str(json_out),
            "--output-images",
            str(img_dir),
        ]
        res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 0, f"CLI failed: {res.stderr}"

        # Verify JSON report
        assert json_out.is_file()
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["sample_size"] == 4
        assert "clean_baseline" in data
        assert "corrupted_evaluation" in data

        # Verify image files
        saved_images = list(img_dir.glob("*.png"))
        assert len(saved_images) == 8  # 4 clean + 4 corrupted


# ---------------------------------------------------------------------------
# Test Line-Boundary Preservation in RealTesseractEngine
# ---------------------------------------------------------------------------


class TestLineBoundaryPreservation:
    """Verify that RealTesseractEngine groups words by (page, line) for field extraction."""

    @staticmethod
    def _make_engine():
        """Create a RealTesseractEngine with mocked availability (no real binary needed)."""
        engine = RealTesseractEngine.__new__(RealTesseractEngine)
        engine.language = "eng"
        engine._available = True
        engine.engine_version = "5.5.3"
        engine._available_languages = {"eng"}
        engine.engine_name = "tesseract"
        return engine

    def test_words_on_different_lines_produce_newline_text(self):
        """Words on distinct line_numbers are joined by newlines, not spaces."""
        from unittest.mock import MagicMock, patch

        engine = self._make_engine()

        # Mock OCRWord-like objects on two different lines
        w1 = MagicMock(text="Institution", confidence=0.95, page_number=1, line_number=1)
        w2 = MagicMock(text="Name:", confidence=0.95, page_number=1, line_number=1)
        w3 = MagicMock(text="Alpha", confidence=0.9, page_number=1, line_number=1)
        w4 = MagicMock(text="Certificate", confidence=0.95, page_number=1, line_number=2)
        w5 = MagicMock(text="No:", confidence=0.95, page_number=1, line_number=2)
        w6 = MagicMock(text="CERT/2026/0001", confidence=0.9, page_number=1, line_number=2)

        mock_raw = MagicMock()
        mock_raw.words = [w1, w2, w3, w4, w5, w6]

        mock_adapter = MagicMock()
        mock_adapter.recognize.return_value = mock_raw

        with patch("backend.app.ocr_pipeline.TesseractOCRAdapter", return_value=mock_adapter), \
             patch("backend.app.ocr_pipeline.extract_institution_fields", return_value={}) as mock_extract:
            engine.extract_from_bytes(b"fake_image_bytes")

        # Verify the text passed to extract_institution_fields has newlines
        text_arg = mock_extract.call_args[0][0]
        assert "\n" in text_arg
        lines = text_arg.split("\n")
        assert len(lines) == 2
        assert lines[0] == "Institution Name: Alpha"
        assert lines[1] == "Certificate No: CERT/2026/0001"

    def test_multiple_fields_different_pages(self):
        """Words on different pages are separated by newlines and sorted correctly."""
        from unittest.mock import MagicMock, patch

        engine = self._make_engine()

        w1 = MagicMock(text="Page1Line1", confidence=0.9, page_number=1, line_number=1)
        w2 = MagicMock(text="Page2Line1", confidence=0.9, page_number=2, line_number=1)
        w3 = MagicMock(text="Page1Line2", confidence=0.9, page_number=1, line_number=2)

        mock_raw = MagicMock()
        mock_raw.words = [w1, w2, w3]

        mock_adapter = MagicMock()
        mock_adapter.recognize.return_value = mock_raw

        with patch("backend.app.ocr_pipeline.TesseractOCRAdapter", return_value=mock_adapter), \
             patch("backend.app.ocr_pipeline.extract_institution_fields", return_value={}) as mock_extract:
            engine.extract_from_bytes(b"fake")

        text_arg = mock_extract.call_args[0][0]
        lines = text_arg.split("\n")
        # Sorted by (page, line): (1,1), (1,2), (2,1)
        assert len(lines) == 3
        assert lines[0] == "Page1Line1"
        assert lines[1] == "Page1Line2"
        assert lines[2] == "Page2Line1"

    def test_empty_ocr_output(self):
        """Zero words → empty transcription and empty fields."""
        from unittest.mock import MagicMock, patch

        engine = self._make_engine()

        mock_raw = MagicMock()
        mock_raw.words = []

        mock_adapter = MagicMock()
        mock_adapter.recognize.return_value = mock_raw

        with patch("backend.app.ocr_pipeline.TesseractOCRAdapter", return_value=mock_adapter), \
             patch("backend.app.ocr_pipeline.extract_institution_fields", return_value={}) as mock_extract:
            result = engine.extract_from_bytes(b"fake")

        text_arg = mock_extract.call_args[0][0]
        assert text_arg == ""
        assert result["transcription"] == ""
        assert result["fields"] == {}
        assert result["confidence"] == 0.0

    def test_language_override(self):
        """The language keyword argument overrides the engine's default language."""
        from unittest.mock import MagicMock, patch

        engine = self._make_engine()

        mock_raw = MagicMock()
        mock_raw.words = []

        mock_adapter = MagicMock()
        mock_adapter.recognize.return_value = mock_raw

        with patch("backend.app.ocr_pipeline.TesseractOCRAdapter", return_value=mock_adapter) as MockCls, \
             patch("backend.app.ocr_pipeline.extract_institution_fields", return_value={}):
            engine.extract_from_bytes(b"fake", language="hin")

        MockCls.assert_called_once_with(language="hin")

    def test_default_language_used_when_no_override(self):
        """Without a language override, the engine's default language is used."""
        from unittest.mock import MagicMock, patch

        engine = self._make_engine()
        engine.language = "eng+hin"

        mock_raw = MagicMock()
        mock_raw.words = []

        mock_adapter = MagicMock()
        mock_adapter.recognize.return_value = mock_raw

        with patch("backend.app.ocr_pipeline.TesseractOCRAdapter", return_value=mock_adapter) as MockCls, \
             patch("backend.app.ocr_pipeline.extract_institution_fields", return_value={}):
            engine.extract_from_bytes(b"fake")

        MockCls.assert_called_once_with(language="eng+hin")


# ---------------------------------------------------------------------------
# Test Language Mapping and Availability
# ---------------------------------------------------------------------------


class TestLanguageMapping:
    def test_dataset_lang_to_tesseract_mapping(self):
        assert DATASET_LANG_TO_TESSERACT["en"] == "eng"
        # Hindi documents also contain Latin values (certificate numbers,
        # institution names, ISO dates), so both packs are required.
        assert DATASET_LANG_TO_TESSERACT["hi"] == "hin+eng"
        assert DATASET_LANG_TO_TESSERACT["bilingual"] == "eng+hin"

    def test_has_language_single_pack(self):
        engine = RealTesseractEngine.__new__(RealTesseractEngine)
        engine._available = True
        engine._available_languages = {"eng", "hin"}
        assert engine.has_language("eng") is True
        assert engine.has_language("hin") is True
        assert engine.has_language("fra") is False

    def test_has_language_composite_pack(self):
        engine = RealTesseractEngine.__new__(RealTesseractEngine)
        engine._available = True
        engine._available_languages = {"eng", "hin"}
        assert engine.has_language("eng+hin") is True
        assert engine.has_language("eng+fra") is False

    def test_has_language_empty_set_assumes_available(self):
        """When we can't retrieve language list, assume available if binary exists."""
        engine = RealTesseractEngine.__new__(RealTesseractEngine)
        engine._available = True
        engine._available_languages = set()
        assert engine.has_language("eng") is True
        assert engine.has_language("anything") is True

    def test_has_language_empty_set_unavailable_binary(self):
        engine = RealTesseractEngine.__new__(RealTesseractEngine)
        engine._available = False
        engine._available_languages = set()
        assert engine.has_language("eng") is False


# ---------------------------------------------------------------------------
# Test Enhanced Report Structure
# ---------------------------------------------------------------------------


class TestEnhancedReport:
    def test_report_contains_per_case_results(self):
        """Mock benchmark report includes case_results list."""
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=4, seed=42)
        engine = MockRasterOCREngine()
        report = RasterBenchmarkScorer.run_benchmark(cases, engine)

        assert "case_results" in report
        assert len(report["case_results"]) == 4
        for cr in report["case_results"]:
            assert cr["status"] == "evaluated"
            assert "case_id" in cr
            assert "language" in cr
            assert "layout" in cr
            assert "corruption_type" in cr
            assert "clean" in cr
            assert "corrupted" in cr
            assert "expected_text" in cr
            assert "expected_fields" in cr
            # Per-case metrics
            assert "cer" in cr["clean"]
            assert "wer" in cr["clean"]
            assert "f1" in cr["clean"]
            assert "predicted_text" in cr["clean"]
            assert "predicted_fields" in cr["clean"]

    def test_report_contains_engine_type_mock(self):
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=2, seed=42)
        engine = MockRasterOCREngine()
        report = RasterBenchmarkScorer.run_benchmark(cases, engine)
        assert report["engine_type"] == "mock"

    def test_report_contains_dataset_fingerprint(self):
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=2, seed=42)
        engine = MockRasterOCREngine()
        report = RasterBenchmarkScorer.run_benchmark(cases, engine)
        assert "dataset_fingerprint" in report
        assert report["dataset_fingerprint"] != "unknown"

    def test_report_counts_match(self):
        """total_cases, evaluated_count, unavailable_count are consistent."""
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=6, seed=42)
        engine = MockRasterOCREngine()
        report = RasterBenchmarkScorer.run_benchmark(cases, engine)
        assert report["total_cases"] == 6
        assert report["evaluated_count"] == 6
        assert report["unavailable_count"] == 0
        assert report["sample_size"] == 6

    def test_unavailable_language_cases_excluded(self):
        """Cases requiring missing language packs are excluded from scoring."""
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=3, seed=42)
        # Force all cases to require Hindi
        for c in cases:
            c["language"] = "hi"

        engine = RealTesseractEngine.__new__(RealTesseractEngine)
        engine.language = "eng"
        engine._available = True
        engine.engine_version = "5.5.3"
        engine._available_languages = {"eng"}  # hin NOT available
        engine.engine_name = "tesseract"

        report = RasterBenchmarkScorer.run_benchmark(cases, engine)
        assert report["available"] is True
        assert report["evaluated_count"] == 0
        assert report["unavailable_count"] == 3
        assert len(report.get("unavailable_cases", [])) == 3
        for uc in report["unavailable_cases"]:
            assert uc["status"] == "unavailable"
            assert "hin" in uc["reason"]

    def test_mixed_available_unavailable_cases(self):
        """Only unavailable cases are excluded; available ones are scored normally."""
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=6, seed=42)
        # Make cases 0,1,2 English (available), 3,4,5 Hindi (unavailable)
        for i, c in enumerate(cases):
            c["language"] = "en" if i < 3 else "hi"

        engine = RealTesseractEngine.__new__(RealTesseractEngine)
        engine.language = "eng"
        engine._available = True
        engine.engine_version = "5.5.3"
        engine._available_languages = {"eng"}
        engine.engine_name = "tesseract"

        # Mock the extract_from_bytes to avoid needing real Tesseract
        from unittest.mock import patch, MagicMock

        mock_raw = MagicMock()
        mock_raw.words = []
        mock_adapter = MagicMock()
        mock_adapter.recognize.return_value = mock_raw

        with patch("backend.app.ocr_pipeline.TesseractOCRAdapter", return_value=mock_adapter), \
             patch("backend.app.ocr_pipeline.extract_institution_fields", return_value={}):
            report = RasterBenchmarkScorer.run_benchmark(cases, engine)

        assert report["total_cases"] == 6
        assert report["evaluated_count"] == 3
        assert report["unavailable_count"] == 3


# ---------------------------------------------------------------------------
# Test Field Scoring Edge Cases
# ---------------------------------------------------------------------------


class TestFieldScoringEdgeCases:
    def test_false_positive_unexpected_field(self):
        """Predicted field not in expected → FP."""
        result = RasterBenchmarkScorer.evaluate_case(
            predicted_text="hello",
            expected_text="hello",
            predicted_fields={"extra_field": "value"},
            expected_fields={},
        )
        assert result["fp"] == 1
        assert result["tp"] == 0
        assert result["fn"] == 0

    def test_false_negative_missing_field(self):
        """Expected field not in predicted → FN."""
        result = RasterBenchmarkScorer.evaluate_case(
            predicted_text="hello",
            expected_text="hello",
            predicted_fields={},
            expected_fields={"institution_name": "Alpha"},
        )
        assert result["fn"] == 1
        assert result["tp"] == 0
        assert result["fp"] == 0

    def test_wrong_value_counts_as_fp_and_fn(self):
        """Mismatched value → both FP and FN."""
        result = RasterBenchmarkScorer.evaluate_case(
            predicted_text="hello",
            expected_text="hello",
            predicted_fields={"institution_name": "Beta"},
            expected_fields={"institution_name": "Alpha"},
        )
        assert result["fp"] == 1
        assert result["fn"] == 1
        assert result["tp"] == 0

    def test_empty_both_fields_no_counts(self):
        """Both empty field dicts → no TP, FP, FN."""
        result = RasterBenchmarkScorer.evaluate_case(
            predicted_text="",
            expected_text="",
            predicted_fields={},
            expected_fields={},
        )
        assert result["tp"] == 0
        assert result["fp"] == 0
        assert result["fn"] == 0

    def test_multiple_fields_mixed_outcomes(self):
        """Mix of TP, FP, FN across multiple fields."""
        result = RasterBenchmarkScorer.evaluate_case(
            predicted_text="hello",
            expected_text="hello",
            predicted_fields={
                "institution_name": "Alpha",  # correct → TP
                "certificate_number": "WRONG",  # wrong value → FP + FN
                "extra_field": "surprise",  # unexpected → FP
            },
            expected_fields={
                "institution_name": "Alpha",
                "certificate_number": "CERT/001",
                "academic_year": "2026-2027",  # missing → FN
            },
        )
        assert result["tp"] == 1
        assert result["fp"] == 2  # wrong cert + extra field
        assert result["fn"] == 2  # wrong cert + missing year


# ---------------------------------------------------------------------------
# Test CLI Edge Cases
# ---------------------------------------------------------------------------


class TestCLIEdgeCases:
    def test_invalid_count_zero(self, tmp_path):
        import subprocess

        cmd = [sys.executable, "ai/raster_benchmark.py", "--count", "0"]
        res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 1
        assert "must be at least 1" in res.stderr

    def test_invalid_count_negative(self, tmp_path):
        import subprocess

        cmd = [sys.executable, "ai/raster_benchmark.py", "--count", "-5"]
        res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 1
        assert "must be at least 1" in res.stderr

    def test_json_parent_dir_created_automatically(self, tmp_path):
        """JSON output directory is created if it doesn't exist."""
        import subprocess

        json_out = tmp_path / "nested" / "deep" / "report.json"
        cmd = [
            sys.executable,
            "ai/raster_benchmark.py",
            "--count", "2",
            "--seed", "42",
            "--json", str(json_out),
        ]
        res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 0, f"CLI failed: {res.stderr}"
        assert json_out.is_file()
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["sample_size"] == 2
        assert "seed" in data

    def test_deterministic_report_same_seed(self, tmp_path):
        """Same seed and count produce identical reports across separate processes.

        The mock engine uses hashlib (not hash()) for field degradation, so
        results are deterministic regardless of PYTHONHASHSEED.
        """
        import subprocess

        reports = []
        for i in range(2):
            json_out = tmp_path / f"report_{i}.json"
            cmd = [
                sys.executable,
                "ai/raster_benchmark.py",
                "--count", "4",
                "--seed", "99",
                "--json", str(json_out),
            ]
            res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
            assert res.returncode == 0
            reports.append(json.loads(json_out.read_text(encoding="utf-8")))

        # Compare everything except timing
        for key in ["clean_baseline", "corrupted_evaluation", "by_corruption_type",
                     "by_language", "dataset_fingerprint", "sample_size"]:
            assert reports[0][key] == reports[1][key], f"Mismatch on {key}"


# ---------------------------------------------------------------------------
# Test Engine Error Handling
# ---------------------------------------------------------------------------


class TestEngineErrorHandling:
    def test_engine_exception_recorded_as_error(self):
        """Engine that raises during evaluation produces error case result."""
        from ai.raster_benchmark import RasterOCREngine

        class FailingEngine(RasterOCREngine):
            engine_name = "failing"

            def is_available(self):
                return True

            def extract_from_bytes(self, image_bytes):
                raise RuntimeError("engine crashed")

        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=2, seed=42)
        engine = FailingEngine()
        report = RasterBenchmarkScorer.run_benchmark(cases, engine)

        assert report["available"] is True
        assert report["evaluated_count"] == 0
        assert len(report["case_results"]) == 2
        for cr in report["case_results"]:
            assert cr["status"] == "error"
            assert "engine crashed" in cr["reason"]

    def test_unavailable_engine_returns_error_report(self):
        """Unavailable engine produces available=False report."""
        from ai.raster_benchmark import RasterOCREngine

        class UnavailableEngine(RasterOCREngine):
            engine_name = "missing"

            def is_available(self):
                return False

            def extract_from_bytes(self, image_bytes):
                raise NotImplementedError

        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=2, seed=42)
        engine = UnavailableEngine()
        report = RasterBenchmarkScorer.run_benchmark(cases, engine)

        assert report["available"] is False
        assert "unavailable" in report["error"]
        assert report["total_cases"] == 2


# ---------------------------------------------------------------------------
# Test measurement honesty, script coverage and language override
# ---------------------------------------------------------------------------


def _mock_available_engine(languages: set[str]) -> RealTesseractEngine:
    """Build a RealTesseractEngine that reports the given installed packs."""
    engine = RealTesseractEngine.__new__(RealTesseractEngine)
    engine.language = "eng"
    engine.override_language = False
    engine._available = True
    engine.engine_version = "test"
    engine._available_languages = set(languages)
    engine.engine_name = "tesseract"
    return engine


class TestMeasurementHonesty:
    def test_no_scored_cases_yields_null_metrics_not_zero(self):
        """A run that scored nothing must report null metrics, not 0.0 (a perfect score)."""
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=3, seed=42)
        for c in cases:
            c["language"] = "hi"
        report = RasterBenchmarkScorer.run_benchmark(cases, _mock_available_engine({"eng"}))

        assert report["evaluated_count"] == 0
        assert report["metrics_available"] is False
        for block in (report["clean_baseline"], report["corrupted_evaluation"]):
            assert block["scored_cases"] == 0
            assert block["cer"] is None
            assert block["wer"] is None
            assert block["f1"] is None
        assert report["degradation_delta"] == {
            "cer_increase": None,
            "wer_increase": None,
            "f1_drop": None,
        }

    def test_scored_aggregates_include_case_count(self):
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=3, seed=42)
        report = RasterBenchmarkScorer.run_benchmark(cases, MockRasterOCREngine())
        assert report["metrics_available"] is True
        assert report["clean_baseline"]["scored_cases"] == 3
        assert report["corrupted_evaluation"]["scored_cases"] == 3
        assert report["corrupted_count"] == 3

    def test_cli_exits_2_when_nothing_can_be_scored(self, tmp_path, monkeypatch):
        """The CLI must not present an empty measurement as a successful report."""
        import ai.raster_benchmark as rb

        empty_block = {
            "scored_cases": 0,
            "cer": None,
            "wer": None,
            "exact": None,
            "precision": None,
            "recall": None,
            "f1": None,
        }
        fake_report = {
            "available": True,
            "engine": "tesseract",
            "engine_type": "real",
            "engine_version": "test",
            "evaluated_count": 0,
            "total_cases": 3,
            "duration_seconds": 0.0,
            "metrics_available": False,
            "render_fonts": {},
            "clean_baseline": dict(empty_block),
            "corrupted_evaluation": dict(empty_block),
            "degradation_delta": {"cer_increase": None, "wer_increase": None, "f1_drop": None},
            "by_corruption_type": {},
            "by_language": {},
            "case_results": [],
        }

        monkeypatch.setattr(rb.RasterBenchmarkScorer, "run_benchmark", classmethod(lambda cls, cases, engine: fake_report))
        monkeypatch.setattr(rb, "MockRasterOCREngine", MockRasterOCREngine)
        monkeypatch.setattr(sys, "argv", ["raster_benchmark.py", "--count", "3"])

        rc = rb.main()
        assert rc == 2


class TestScriptCoverage:
    def test_devanagari_languages_declared(self):
        assert DEVANAGARI_LANGUAGES == {"hi", "bilingual"}

    def test_english_is_always_renderable(self):
        assert script_is_renderable("en") is True

    def test_devanagari_renderability_follows_font_resolution(self, monkeypatch):
        monkeypatch.delenv(DEVANAGARI_FONT_ENV, raising=False)
        monkeypatch.setattr("ai.raster_benchmark._DEVANAGARI_FONT_CANDIDATES", [])
        monkeypatch.setattr("ai.raster_benchmark._FONT_SEARCH_DIRS", ())
        assert resolve_render_font("hi") is None
        assert script_is_renderable("hi") is False

    def test_env_override_font_is_used(self, monkeypatch, tmp_path):
        from PIL import ImageFont

        font_path = tmp_path / "NotoSansDevanagari.ttf"
        source = None
        for candidate in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ):
            if Path(candidate).is_file():
                source = candidate
                break
        assert source is not None, "no usable font on this host to build the fixture"
        font_path.write_bytes(Path(source).read_bytes())
        # The copied file must still load as a font for the override to be usable.
        ImageFont.truetype(str(font_path), 12)

        monkeypatch.setenv(DEVANAGARI_FONT_ENV, str(font_path))
        assert resolve_render_font("hi") == str(font_path)
        assert script_is_renderable("bilingual") is True

    def test_missing_font_marks_hindi_cases_unavailable(self, monkeypatch):
        """With the language pack present but no Devanagari font, cases are excluded."""
        monkeypatch.delenv(DEVANAGARI_FONT_ENV, raising=False)
        monkeypatch.setattr("ai.raster_benchmark._DEVANAGARI_FONT_CANDIDATES", [])
        monkeypatch.setattr("ai.raster_benchmark._FONT_SEARCH_DIRS", ())

        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=3, seed=42)
        for c in cases:
            c["language"] = "hi"

        report = RasterBenchmarkScorer.run_benchmark(cases, _mock_available_engine({"eng", "hin"}))
        assert report["evaluated_count"] == 0
        assert report["unavailable_count"] == 3
        for uc in report["unavailable_cases"]:
            assert "Devanagari" in uc["reason"]
            assert DEVANAGARI_FONT_ENV in uc["reason"]

    def test_generated_case_records_render_font_and_coverage(self):
        doc_en = RasterDocumentGenerator.generate_document(case_idx=1, language="en", seed=7)
        assert doc_en["script_renderable"] is True
        doc_hi = RasterDocumentGenerator.generate_document(case_idx=2, language="hi", seed=7)
        assert doc_hi["script_renderable"] is script_is_renderable("hi")
        assert doc_hi["render_font"] == resolve_render_font("hi")

    def test_report_records_render_fonts_per_language(self):
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=3, seed=42)
        report = RasterBenchmarkScorer.run_benchmark(cases, MockRasterOCREngine())
        assert set(report["render_fonts"]) == {"en", "bilingual", "hi"}


class TestLanguageOverride:
    def test_default_maps_each_case_by_dataset_language(self):
        engine = _mock_available_engine({"eng", "hin"})
        assert tesseract_language_for(engine, "en") == "eng"
        assert tesseract_language_for(engine, "hi") == "hin+eng"
        assert tesseract_language_for(engine, "bilingual") == "eng+hin"

    def test_explicit_override_wins_for_every_case(self):
        engine = _mock_available_engine({"eng", "hin"})
        engine.language = "eng"
        engine.override_language = True
        assert tesseract_language_for(engine, "hi") == "eng"
        assert tesseract_language_for(engine, "bilingual") == "eng"

    def test_override_requires_explicit_flag(self):
        engine = _mock_available_engine({"eng", "hin"})
        engine.language = "hin"
        assert tesseract_language_for(engine, "en") == "eng"


class TestMockDeterminism:
    def test_same_image_bytes_produce_identical_output(self):
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=3, seed=42)
        engine = MockRasterOCREngine()
        case = cases[1]
        first = engine.extract_from_bytes(
            case["corrupted_image_bytes"],
            reference_text=case["transcription_ground_truth"],
            reference_fields=case["ground_truth"],
            corruption_type="skew",
        )
        second = engine.extract_from_bytes(
            case["corrupted_image_bytes"],
            reference_text=case["transcription_ground_truth"],
            reference_fields=case["ground_truth"],
            corruption_type="skew",
        )
        assert first == second

    def test_seed_is_digest_derived_not_length_derived(self):
        """Equal-length but different bytes must not produce identical degradations."""
        engine = MockRasterOCREngine({"skew": 0.5})
        reference = "Institution Name: Alpha Institute of Technology " * 8
        bytes_a = b"\x89PNG" + b"A" * 200
        bytes_b = b"\x89PNG" + b"B" * 200
        assert len(bytes_a) == len(bytes_b)
        out_a = engine.extract_from_bytes(bytes_a, reference_text=reference, corruption_type="skew")
        out_b = engine.extract_from_bytes(bytes_b, reference_text=reference, corruption_type="skew")
        assert out_a["transcription"] != out_b["transcription"]


class TestFieldScoringNulls:
    def test_null_expected_and_predicted_values_are_not_counted(self):
        result = RasterBenchmarkScorer.evaluate_case(
            predicted_text="text",
            expected_text="text",
            predicted_fields={"institution_name": None},
            expected_fields={"institution_name": None},
        )
        assert result["tp"] == 0
        assert result["fp"] == 0
        assert result["fn"] == 0

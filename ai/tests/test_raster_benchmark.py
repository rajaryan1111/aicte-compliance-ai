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

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.raster_benchmark import (  # noqa: E402
    DATASET_LANG_TO_TESSERACT,
    SUPPORTED_IMAGE_CORRUPTIONS,
    MockRasterOCREngine,
    RasterBenchmarkScorer,
    RasterDocumentGenerator,
    RealTesseractEngine,
    apply_gaussian_blur,
    apply_jpeg_compression,
    apply_low_contrast,
    apply_low_resolution,
    apply_noise,
    apply_raster_corruption,
    apply_rotation,
    apply_skew,
    character_error_rate,
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
        engine.psm = 6
        engine.psm = 6
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
        assert DATASET_LANG_TO_TESSERACT["hi"] == "hin"
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
        engine.psm = 6
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
        engine.psm = 6
        engine._available = True
        engine.engine_version = "5.5.3"
        engine._available_languages = {"eng"}
        engine.engine_name = "tesseract"

        # Mock the extract_from_bytes to avoid needing real Tesseract
        from unittest.mock import MagicMock, patch

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


class TestFontGlyphCoverage:
    """Regression tests for the tofu-font glyph-coverage check.

    DevanagariMT.ttc face 0 contains digits but no Latin letters and renders
    every missing letter as the same shared "tofu" box; using it for English
    documents made every letter OCR as O/0 while digits stayed correct.  The
    font loader must reject such fonts by probing rendered bitmaps.
    """

    SAMPLES = "ABCDEfgqr123"

    def _render_char(self, font, ch):
        from PIL import Image, ImageDraw

        scratch = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(scratch).text((8, 8), ch, fill=255, font=font)
        return scratch.tobytes()

    def test_english_font_renders_latin_distinctly(self):
        """_get_font('en') must return a font whose Latin glyphs are all distinct."""
        from ai.raster_benchmark import _get_font

        font = _get_font(24, "en")
        bitmaps = [self._render_char(font, ch) for ch in self.SAMPLES]
        assert all(any(b) for b in bitmaps), "glyph must not be empty"
        assert len(set(bitmaps)) == len(self.SAMPLES), (
            "distinct Latin characters must render as distinct glyphs (no tofu box)"
        )

    def test_hindi_font_renders_devanagari_and_latin(self):
        """_get_font('hi') must cover Devanagari AND basic Latin on one line."""
        from ai.raster_benchmark import _get_font

        font = _get_font(24, "hi")
        deva = [self._render_char(font, ch) for ch in "कखगसहड"]
        # All-distinct characters: repeated characters legitimately render
        # identical bitmaps, so the sample for the distinctness check must not
        # contain duplicates (the same trap as the duplicated '2' in CERT2026).
        latin = [self._render_char(font, ch) for ch in "CERT0185"]
        assert len(set(deva)) == len(deva), "Devanagari glyphs must be distinct"
        assert len(set(latin)) == len(latin), (
            "mixed-line Latin (CERT/2026/...) values must render as distinct glyphs"
        )

    def test_font_probe_rejects_latin_tofu_font(self):
        """The probe rejects DevanagariMT: it boxes every Latin letter identically.

        This is the real font that produced the original defect (letters OCR'd
        as O/0 while digits stayed correct) — used directly as evidence.
        """
        import os

        from PIL import ImageFont

        from ai.raster_benchmark import _LATIN_SAMPLE, _font_renders_sample

        devanagari_mt = "/System/Library/Fonts/Supplemental/DevanagariMT.ttc"
        if not os.path.isfile(devanagari_mt):
            pytest.skip("DevanagariMT.ttc not present on this host")
        font = ImageFont.truetype(devanagari_mt, 24)
        assert _font_renders_sample(font, _LATIN_SAMPLE) is False

    def test_font_probe_rejects_missing_devanagari(self):
        """The probe rejects a Latin-only font as a provider for Devanagari."""
        import os

        from PIL import ImageFont

        from ai.raster_benchmark import _DEVANAGARI_SAMPLE, _font_renders_sample

        arial = "/System/Library/Fonts/Supplemental/Arial.ttf"
        if not os.path.isfile(arial):
            pytest.skip("Arial.ttf not present on this host")
        font = ImageFont.truetype(arial, 24)
        assert _font_renders_sample(font, _DEVANAGARI_SAMPLE) is False

    def test_font_probe_accepts_real_font(self):
        """A standard font passes the probe for its supported script."""
        import os

        from PIL import ImageFont

        from ai.raster_benchmark import _LATIN_SAMPLE, _font_renders_sample

        if not os.path.isfile(ARIAL_FOR_TESTS):
            pytest.skip("no system font available for the positive probe")
        font = ImageFont.truetype(ARIAL_FOR_TESTS, 24)
        assert _font_renders_sample(font, _LATIN_SAMPLE) is True


# First available font used for the positive-probe test across hosts.
ARIAL_FOR_TESTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
][0]


# ---------------------------------------------------------------------------
# Pooled multi-seed benchmark (run_benchmark_multiseed)
# ---------------------------------------------------------------------------


class TestMultiSeedBenchmark:
    """Regression tests for pooled multi-seed evaluation."""

    def _run(self, seeds, count=4):
        from ai.raster_benchmark import MockRasterOCREngine, run_benchmark_multiseed

        return run_benchmark_multiseed(seeds, count=count, engine=MockRasterOCREngine())

    # -- seed validation ----------------------------------------------------

    def test_multiseed_rejects_duplicate_seeds(self):
        with pytest.raises(ValueError, match="[Dd]uplicate seeds"):
            self._run([42, 42, 43])

    def test_multiseed_rejects_empty_seed_list(self):
        with pytest.raises(ValueError, match="at least one seed"):
            self._run([])

    # -- dataset independence ------------------------------------------------

    def test_multiseed_datasets_are_distinct(self):
        report = self._run([42, 43, 44])
        fps = [r["dataset_fingerprint"] for r in report["per_seed"]]
        assert len(set(fps)) == 3, "same count with different seeds must yield distinct datasets"

    # -- reconciliation -------------------------------------------------------

    def test_multiseed_counts_reconcile(self):
        report = self._run([42, 43], count=4)
        assert report["total_case_pairs"] == 8
        assert (
            report["evaluated_pairs"] + report["unavailable_pairs"] + report["failed_pairs"]
            == report["total_case_pairs"]
        )
        assert report["reconciliation"]["evaluated_plus_unavailable_plus_failed_equals_total"] is True

    # -- pooled math (independent recomputation) ------------------------------

    def test_pooled_corrupted_cer_matches_equal_weight_mean(self):
        """With identical evaluated counts per seed, pooled CER must equal the
        arithmetic mean of per-seed CERs (a hand-checkable restatement of
        case-level micro-averaging)."""
        report = self._run([42, 43], count=4)
        evaluated = [r["evaluated_count"] for r in report["per_seed"]]
        assert len(set(evaluated)) == 1, "mock engine evaluates every case"
        per_seed_cer = [r["corrupted_evaluation"]["cer"] for r in report["per_seed"]]
        expected = round(sum(per_seed_cer) / len(per_seed_cer), 4)
        assert math.isclose(report["pooled"]["corrupted_evaluation"]["cer"], expected, abs_tol=1e-6)

    def test_pooled_delta_positive_and_consistent(self):
        report = self._run([42, 43], count=4)
        pool = report["pooled"]
        delta = pool["degradation_delta"]
        assert pool["corrupted_evaluation"]["cer"] >= pool["clean_baseline"]["cer"]
        assert delta["cer_increase"] >= 0
        assert delta["f1_drop"] >= 0
        assert math.isclose(
            delta["cer_increase"],
            round(pool["corrupted_evaluation"]["cer"] - pool["clean_baseline"]["cer"], 4),
            abs_tol=1e-6,
        )

    # -- per-seed summary stats ----------------------------------------------

    def test_sample_stddev_known_values(self):
        from ai.raster_benchmark import sample_stddev

        # [1, 2, 3] with ddof=1: mean=2, sqrt((1+0+1)/2) = 1.0
        assert sample_stddev([1.0, 2.0, 3.0]) == pytest.approx(1.0)
        assert sample_stddev([4.0]) == 0.0
        assert sample_stddev([]) == 0.0
        assert sample_stddev([5.0, 5.0, 5.0]) == 0.0

    def test_metric_summary_shape_and_values(self):
        from ai.raster_benchmark import _metric_summary

        summary = _metric_summary({"corrupted_cer": [0.1, 0.3]})
        block = summary["corrupted_cer"]
        assert set(block.keys()) == {"mean", "sample_stddev", "min", "max", "seeds"}
        assert block["mean"] == 0.2
        assert block["min"] == 0.1
        assert block["max"] == 0.3
        assert block["seeds"] == 2
        # [0.1, 0.3] ddof=1: sqrt((0.01 + 0.01) / 1) = sqrt(0.02)
        assert block["sample_stddev"] == pytest.approx(math.sqrt(0.02), abs=1e-3)

    def test_metric_summary_skips_empty_metric(self):
        from ai.raster_benchmark import _metric_summary

        summary = _metric_summary({"corrupted_cer": [0.1], "clean_cer": []})
        assert "corrupted_cer" in summary
        assert "clean_cer" not in summary

    # -- report schema ---------------------------------------------------------

    def test_multiseed_report_schema(self):
        report = self._run([42], count=4)
        for key in (
            "seeds",
            "count_per_seed",
            "total_case_pairs",
            "evaluated_pairs",
            "unavailable_pairs",
            "failed_pairs",
            "reconciliation",
            "total_duration_seconds",
            "per_seed",
            "pooled",
            "per_seed_summary",
        ):
            assert key in report, f"multiseed report missing key {key!r}"
        assert report["seeds"] == [42]
        assert report["pooled"]["clean_baseline"]["cer"] == report["per_seed"][0]["clean_baseline"]["cer"]

    # -- CLI integration ---------------------------------------------------------

    def test_cli_multiseed_writes_json(self, tmp_path):
        import subprocess

        json_out = tmp_path / "multiseed.json"
        cmd = [
            sys.executable,
            "ai/raster_benchmark.py",
            "--count",
            "4",
            "--seeds",
            "42,43",
            "--json",
            str(json_out),
        ]
        res = subprocess.run(cmd, check=False, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 0, f"CLI multiseed failed: {res.stderr}"
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["seeds"] == [42, 43]
        assert data["total_case_pairs"] == 8
        assert "per_seed_summary" in data

    def test_cli_rejects_duplicate_seeds(self):
        import subprocess

        cmd = [sys.executable, "ai/raster_benchmark.py", "--seeds", "42,42"]
        res = subprocess.run(cmd, check=False, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 1
        assert "duplicate seeds" in res.stderr.lower()

    def test_cli_rejects_non_integer_seeds(self):
        import subprocess

        cmd = [sys.executable, "ai/raster_benchmark.py", "--seeds", "42,abc"]
        res = subprocess.run(cmd, check=False, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 1
        assert "integers" in res.stderr.lower()


# ---------------------------------------------------------------------------
# Rendering capability / shaping validity signalling
# ---------------------------------------------------------------------------


class TestRenderingCapabilitySignalling:
    """Regression tests: unfaithful (unshaped) Hindi rendering must invalidate
    hi/bilingual measurements in the report instead of being silently scored."""

    def test_rendering_capabilities_shape(self):
        from ai.raster_benchmark import rendering_capabilities

        cap = rendering_capabilities()
        assert set(cap.keys()) == {"raqm", "raqm_version"}
        assert isinstance(cap["raqm"], bool)
        assert cap["raqm_version"] is None or isinstance(cap["raqm_version"], str)

    def test_language_rendering_valid_flags_shaping_languages_without_raqm(self, monkeypatch):
        from ai.raster_benchmark import language_rendering_valid

        monkeypatch.setattr(
            "ai.raster_benchmark.rendering_capabilities",
            lambda: {"raqm": False, "raqm_version": None},
        )
        assert language_rendering_valid("en") is True
        assert language_rendering_valid("hi") is False
        assert language_rendering_valid("bilingual") is False

    def test_language_rendering_valid_all_with_raqm(self, monkeypatch):
        from ai.raster_benchmark import language_rendering_valid

        monkeypatch.setattr(
            "ai.raster_benchmark.rendering_capabilities",
            lambda: {"raqm": True, "raqm_version": "0.10.2"},
        )
        for lang in ("en", "hi", "bilingual"):
            assert language_rendering_valid(lang) is True

    def _run(self, monkeypatch, capabilities, count=4):
        from ai.raster_benchmark import (  # noqa: E402
            MockRasterOCREngine,
            RasterBenchmarkScorer,
            RasterDocumentGenerator,
        )

        monkeypatch.setattr(
            "ai.raster_benchmark.rendering_capabilities",
            lambda: capabilities,
        )
        cases = RasterDocumentGenerator.generate_benchmark_dataset(count=count, seed=42)
        return RasterBenchmarkScorer.run_benchmark(cases, MockRasterOCREngine())

    def test_run_benchmark_flags_unshaped_hindi(self, monkeypatch):
        report = self._run(
            monkeypatch, {"raqm": False, "raqm_version": None}
        )
        assert report["rendering"] == {"raqm": False, "raqm_version": None}
        assert "hi" in report["accuracy_invalid_languages"]
        assert "bilingual" in report["accuracy_invalid_languages"]
        assert report["accuracy_valid"] is False

    def test_run_benchmark_clean_when_raqm_present(self, monkeypatch):
        report = self._run(monkeypatch, {"raqm": True, "raqm_version": "0.10.2"})
        assert report["accuracy_invalid_languages"] == []
        assert report["accuracy_valid"] is True

    def test_multiseed_ignores_seeds_with_invalid_rendering(self, monkeypatch):
        """A seed that evaluated a shaping-limited language must invalidate the
        whole pooled report's accuracy claim for that language."""
        from ai.raster_benchmark import MockRasterOCREngine, run_benchmark_multiseed

        monkeypatch.setattr(
            "ai.raster_benchmark.rendering_capabilities",
            lambda: {"raqm": False, "raqm_version": None},
        )
        report = run_benchmark_multiseed([42, 43], count=4, engine=MockRasterOCREngine())
        assert "hi" in report["accuracy_invalid_languages"]
        for psr in report["per_seed"]:
            assert "hi" in psr["accuracy_invalid_languages"]


# ---------------------------------------------------------------------------
# PSM configuration bake-off support (added for the engine-comparison milestone)
# ---------------------------------------------------------------------------


class TestTesseractPSMConfiguration:
    """RealTesseractEngine PSM selection: contract path vs benchmark-only direct path."""

    @staticmethod
    def _engine(**kwargs):
        """Build via __new__ without requiring the real binary, with minimal state."""
        engine = RealTesseractEngine.__new__(RealTesseractEngine)
        engine.language = "eng"
        engine._available = True
        return engine

    def test_invalid_psm_values_raise(self):
        for bad in (14, -1, "6", True, 6.0, None):
            with pytest.raises(ValueError):
                RealTesseractEngine(language="eng", psm=bad)

    def test_psm_attribute_records_mode(self):
        """A valid psm is stored unmodified on the instance (needs the binary; skip otherwise)."""
        import shutil
        if shutil.which("tesseract") is None:
            pytest.skip("tesseract binary not installed")
        engine = RealTesseractEngine(language="eng", psm=3)
        assert engine.psm == 3
        assert engine.engine_name == "tesseract-psm3"
        engine6 = RealTesseractEngine(language="eng")
        assert engine6.psm == 6
        assert engine6.engine_name == "tesseract"

    def test_default_psm_is_six_and_uses_backend_adapter_label(self):
        engine = self._engine()
        engine.psm = 6
        engine.engine_name = RealTesseractEngine.engine_name
        from unittest.mock import MagicMock, patch

        mock_word = MagicMock(text="Hi", confidence=95.0, page_number=1, line_number=1)
        mock_raw = MagicMock(words=[mock_word])
        with patch(
            "backend.app.ocr_pipeline.TesseractOCRAdapter",
            return_value=MagicMock(recognize=MagicMock(return_value=mock_raw)),
        ) as mock_adapter_cls, patch(
            "backend.app.ocr_pipeline.extract_institution_fields", return_value={}
        ):
            result = engine.extract_from_bytes(b"img")
        assert mock_adapter_cls.call_args.kwargs.get("language") == "eng"
        assert result["engine"] == "tesseract"
        assert result["psm"] == 6
        assert result["recognition_vehicle"] == "backend_adapter"

    def test_psm3_runs_direct_path_with_config_and_label(self, monkeypatch):
        engine = self._engine()
        engine.psm = 3
        engine.engine_name = "tesseract-psm3"
        engine.engine_version = "5.5.3"

        pytesseract = pytest.importorskip("pytesseract")

        data = {
            "text": ["Institution", "Name:", "Alpha", "Certificate", "No:", "CERT/2026/0001"],
            "conf": [95, 95, 90, 95, 95, 90],
            "page_num": [1, 1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 2, 2, 2],
        }
        calls = {}

        def fake_image_to_data(image, lang, config, output_type):
            calls["config"] = config
            calls["lang"] = lang
            return data

        monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)
        # A real decodable PNG so the mirrored preprocessing passes.
        import io as _io
        from PIL import Image as _PILImage

        buf = _io.BytesIO()
        _PILImage.new("L", (8, 8), 255).save(buf, format="PNG")
        result = engine.extract_from_bytes(buf.getvalue())
        assert calls["config"] == "--psm 3"
        assert calls["lang"] == "eng"
        assert result["engine"] == "tesseract-psm3"
        assert result["recognition_vehicle"] == "direct_pytesseract"
        assert result["transcription"] == "Institution Name: Alpha\nCertificate No: CERT/2026/0001"

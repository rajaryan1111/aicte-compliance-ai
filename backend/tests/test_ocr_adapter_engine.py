"""Adapter-level regression tests for optional Tesseract handling.

A stub ``pytesseract`` module is injected, so these tests exercise our own error
mapping and result validation only. They are not a real-engine or accuracy test;
that smoke test lives in ``test_ocr_engine_integration.py``.
"""
from __future__ import annotations

import io
import sys
import types

import pytest
from PIL import Image

from backend.app.ocr_pipeline import OCRInputError, TesseractOCRAdapter


def image_bytes(format_name: str = "PNG", size: tuple[int, int] = (80, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=format_name)
    return buffer.getvalue()


@pytest.fixture
def install_stub(monkeypatch):
    def install(**overrides):
        module = types.ModuleType("pytesseract")
        module.Output = types.SimpleNamespace(DICT="dict")
        module.get_tesseract_version = lambda: "5.3.0"
        module.image_to_data = lambda *args, **kwargs: {
            "text": [],
            "conf": [],
            "page_num": [],
            "line_num": [],
        }
        for name, value in overrides.items():
            setattr(module, name, value)
        monkeypatch.setitem(sys.modules, "pytesseract", module)
        return module

    return install


def test_non_finite_negative_and_malformed_confidence_is_dropped(install_stub):
    install_stub(
        image_to_data=lambda *args, **kwargs: {
            "text": ["Institution", "Name:", "Example", "College", "Extra"],
            "conf": [float("nan"), float("inf"), "-1", "55", "not-a-number"],
            "page_num": [1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 1, 1],
        }
    )

    result = TesseractOCRAdapter().recognize(image_bytes())

    assert [(word.text, word.confidence) for word in result.words] == [("College", 0.55)]
    assert result.engine == "tesseract"
    assert result.engine_version == "5.3.0"


def test_confidence_above_100_is_discarded_never_inflated(install_stub):
    """A malformed engine score must not become maximum confidence."""
    install_stub(
        image_to_data=lambda *args, **kwargs: {
            "text": ["Institution"],
            "conf": ["150"],
            "page_num": [1],
            "line_num": [1],
        }
    )

    result = TesseractOCRAdapter().recognize(image_bytes())

    assert result.words == ()


def test_malformed_page_and_line_numbers_fall_back_to_one(install_stub):
    install_stub(
        image_to_data=lambda *args, **kwargs: {
            "text": ["Institution"],
            "conf": ["90"],
            "page_num": ["bad"],
            "line_num": [None],
        }
    )

    result = TesseractOCRAdapter().recognize(image_bytes())

    assert (result.words[0].page_number, result.words[0].line_number) == (1, 1)


def test_truncated_image_is_an_input_error_and_never_reaches_the_engine(install_stub):
    calls: list[int] = []
    install_stub(image_to_data=lambda *args, **kwargs: calls.append(1) or {})

    payload = image_bytes("JPEG", (200, 200))
    truncated = payload[: len(payload) // 2]

    with pytest.raises(OCRInputError, match="decoded safely"):
        TesseractOCRAdapter().recognize(truncated)

    assert calls == []


def test_engine_failure_is_reported_as_engine_failure_not_input_error(install_stub):
    def boom(*args, **kwargs):
        raise RuntimeError("tesseract binary unavailable")

    install_stub(image_to_data=boom)

    with pytest.raises(RuntimeError, match="Tesseract OCR failed"):
        TesseractOCRAdapter().recognize(image_bytes())


@pytest.mark.parametrize("language", ["", "e", "en g", "../eng", "eng;rm -rf /"])
def test_adapter_rejects_unsafe_language_codes(language):
    with pytest.raises(ValueError, match="language"):
        TesseractOCRAdapter(language=language)


# --- regression tests added by the 2026-10-23 foundation audit -------------


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not-a-mapping",
        {"text": None, "conf": None, "page_num": None, "line_num": None},
        {"text": "Institution", "conf": "90", "page_num": [1], "line_num": [1]},
        {"text": ["Institution"], "conf": [90], "page_num": 1, "line_num": 1},
    ],
)
def test_malformed_engine_data_raises_runtime_error(install_stub, payload):
    install_stub(image_to_data=lambda *args, **kwargs: payload)

    with pytest.raises(RuntimeError, match="malformed data"):
        TesseractOCRAdapter().recognize(image_bytes())


def test_missing_engine_columns_are_treated_as_empty_not_crashing(install_stub):
    install_stub(image_to_data=lambda *args, **kwargs: {"text": [], "conf": []})

    result = TesseractOCRAdapter().recognize(image_bytes())

    assert result.words == ()


def test_multi_frame_tiff_warns_that_only_the_first_frame_is_read(install_stub):
    install_stub(
        image_to_data=lambda *args, **kwargs: {
            "text": ["Institution"],
            "conf": ["90"],
            "page_num": ["1"],
            "line_num": ["1"],
        }
    )
    buffer = io.BytesIO()
    frames = [Image.new("RGB", (60, 40), "white"), Image.new("RGB", (60, 40), "black")]
    frames[0].save(buffer, format="TIFF", save_all=True, append_images=frames[1:])

    result = TesseractOCRAdapter().recognize(buffer.getvalue())

    assert any("only the first frame" in warning for warning in result.warnings)


def test_single_frame_image_has_no_multi_frame_warning(install_stub):
    install_stub(
        image_to_data=lambda *args, **kwargs: {
            "text": ["Institution"],
            "conf": ["90"],
            "page_num": ["1"],
            "line_num": ["1"],
        }
    )

    result = TesseractOCRAdapter().recognize(image_bytes())

    assert result.warnings == ()


# --- engine output integrity (2026-10-23 follow-up audit) ------------------
# Contract under test:
#   required columns  -> text, conf (present, sequences, equal length)
#   optional columns  -> page_num, line_num (absent => default 1; present =>
#                        must align with text, never silently defaulted)
#   structural violations -> RuntimeError("Tesseract OCR returned malformed data; ...")
#   unusable per-word confidence -> that word is dropped (never clamped)
#   non-string text -> RuntimeError (never stringified)


def _engine_result(**columns):
    """Build a stub engine response, omitting any column passed as _OMIT."""
    return {key: value for key, value in columns.items() if value is not _OMIT}


_OMIT = object()


def _respond(install_stub, payload):
    install_stub(image_to_data=lambda *args, **kwargs: payload)
    return TesseractOCRAdapter().recognize(image_bytes())


BASE_COLUMNS = {
    "text": ["Institution", "Name:", "Example"],
    "conf": ["90", "80", "70"],
    "page_num": [1, 1, 1],
    "line_num": [1, 1, 1],
}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        _engine_result(conf=BASE_COLUMNS["conf"], page_num=[1], line_num=[1]),
        _engine_result(text=BASE_COLUMNS["text"], page_num=[1], line_num=[1]),
    ],
    ids=["empty-mapping", "missing-text", "missing-conf"],
)
def test_missing_required_columns_fail_explicitly(install_stub, payload):
    with pytest.raises(RuntimeError, match="malformed data"):
        _respond(install_stub, payload)


def test_structurally_valid_empty_result_is_not_malformed(install_stub):
    """An empty page is a legitimate result, not an engine failure."""
    for payload in (
        {"text": [], "conf": []},
        {"text": [], "conf": [], "page_num": [], "line_num": []},
    ):
        result = _respond(install_stub, payload)

        assert result.words == ()
        assert result.engine == "tesseract"
        assert result.warnings == ()


@pytest.mark.parametrize(
    ("text", "conf"),
    [
        (["a", "b", "c"], ["90"]),
        (["a", "b", "c"], ["90", "80", "70", "60"]),
        (["a"], []),
    ],
    ids=["conf-shorter", "conf-longer", "conf-empty"],
)
def test_mismatched_required_column_lengths_raise_instead_of_truncating(
    install_stub, text, conf
):
    with pytest.raises(RuntimeError, match="different lengths"):
        _respond(
            install_stub,
            {"text": text, "conf": conf, "page_num": [1] * len(text), "line_num": [1] * len(text)},
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"page_num": [2]},                      # one entry for three words
        {"page_num": [2, 2, 2], "line_num": [1]},  # line column too short
        {"line_num": [1, 2, 3, 4, 5]},          # line column too long
    ],
    ids=["page-short", "line-short", "line-long"],
)
def test_misaligned_optional_metadata_raises_instead_of_misattributing(
    install_stub, metadata
):
    payload = {"text": ["a", "b", "c"], "conf": ["90", "80", "70"], **metadata}

    with pytest.raises(RuntimeError, match="does not align"):
        _respond(install_stub, payload)


def test_absent_optional_metadata_defaults_to_page_and_line_one(install_stub):
    result = _respond(
        install_stub, {"text": ["Institution"], "conf": ["90"]}
    )

    word = result.words[0]
    assert (word.page_number, word.line_number) == (1, 1)


def test_unusable_metadata_values_fall_back_to_one_per_entry(install_stub):
    result = _respond(
        install_stub,
        {
            "text": ["Institution", "Name:", "Example"],
            "conf": ["90", "80", "70"],
            "page_num": ["bad", 0, 2],
            "line_num": [None, -3, 4],
        },
    )

    assert [(w.page_number, w.line_number) for w in result.words] == [(1, 1), (1, 1), (2, 4)]


class _Arbitrary:
    def __str__(self) -> str:  # pragma: no cover - must never be used
        return "fabricated-text"


@pytest.mark.parametrize(
    "bad_text", [None, 123, b"Institution", 4.5, _Arbitrary()],
    ids=["none", "int", "bytes", "float", "object"],
)
def test_non_string_text_is_rejected_never_stringified(install_stub, bad_text):
    with pytest.raises(RuntimeError, match="non-string value"):
        _respond(
            install_stub,
            {
                "text": [bad_text, "Name:"],
                "conf": ["90", "80"],
                "page_num": [1, 1],
                "line_num": [1, 1],
            },
        )


@pytest.mark.parametrize("invalid_confidence", [
    -1, -0.5, 101, 150, float("nan"), float("inf"), float("-inf"),
    "", "abc", None, True, False, _Arbitrary(), "1e999",
])
def test_invalid_confidence_drops_the_word_without_inflation(
    install_stub, invalid_confidence
):
    result = _respond(
        install_stub,
        {
            "text": ["Institution", "Name:"],
            "conf": [invalid_confidence, "80"],
            "page_num": [1, 1],
            "line_num": [1, 1],
        },
    )

    assert [(w.text, w.confidence) for w in result.words] == [("Name:", 0.8)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, 0.0), ("0", 0.0), (100, 1.0), ("100", 1.0), (55, 0.55), ("55.5", 0.555)],
)
def test_valid_tesseract_confidences_keep_their_meaning(
    install_stub, raw, expected
):
    result = _respond(
        install_stub,
        {
            "text": ["Institution"],
            "conf": [raw],
            "page_num": [1],
            "line_num": [1],
        },
    )

    assert result.words[0].confidence == pytest.approx(expected)


def test_engine_error_and_input_error_remain_distinguishable(install_stub):
    install_stub(image_to_data=lambda *args, **kwargs: {})  # malformed columns

    with pytest.raises(RuntimeError, match="malformed data"):
        TesseractOCRAdapter().recognize(image_bytes())

    payload = image_bytes("JPEG", (200, 200))
    with pytest.raises(OCRInputError, match="decoded safely"):
        TesseractOCRAdapter().recognize(payload[: len(payload) // 2])


def test_blank_text_entries_are_skipped_without_failing(install_stub):
    result = _respond(
        install_stub,
        {
            "text": ["", "  ", "Institution"],
            "conf": ["95", "95", "90"],
            "page_num": [1, 1, 1],
            "line_num": [1, 2, 3],
        },
    )

    assert [w.text for w in result.words] == ["Institution"]

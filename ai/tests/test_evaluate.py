"""Tests for the synthetic extraction corpus and its scorer.

Run: `python -m pytest -q ai/tests`

They check three separate things:

1. the scorer's arithmetic is right, on hand-worked examples;
2. the corpus is well formed and its expected values actually match the extractor,
   with known gaps reported rather than silently accepted;
3. the CLI behaves (exit codes, `--check`, JSON output) and always prints the
   synthetic-corpus caveat.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.evaluate_extraction import (  # noqa: E402
    BANNER,
    CORPUS_PATH,
    CaseResult,
    evaluate_case,
    load_corpus,
    run,
    score,
)

SCRIPT = REPO_ROOT / "ai" / "evaluate_extraction.py"
TEXT_FIELDS = {
    "institution_name",
    "certificate_number",
    "application_reference",
    "issue_date",
    "valid_until",
    "academic_year",
}


def result(case_id: str, expected: dict, extracted: dict, known_gap: bool = False) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        category="test",
        expected=expected,
        extracted=extracted,
        known_gap=known_gap,
    )


# --- scorer arithmetic ----------------------------------------------------


def test_perfect_case_scores_one():
    report = score([result("a", {"institution_name": "X"}, {"institution_name": "X"})])
    assert report["per_field"]["institution_name"]["tp"] == 1
    assert report["per_field"]["institution_name"]["fp"] == 0
    assert report["per_field"]["institution_name"]["fn"] == 0
    assert report["micro"]["f1"] == 1.0
    assert report["exact_match_count"] == 1


def test_missing_field_is_a_false_negative_not_a_pass():
    report = score([result("a", {"valid_until": "2027-04-30"}, {})])
    assert report["per_field"]["valid_until"]["fn"] == 1
    assert report["per_field"]["valid_until"]["precision"] == 0.0
    assert report["per_field"]["valid_until"]["recall"] == 0.0
    assert report["exact_match_count"] == 0


def test_wrong_value_counts_as_false_positive_and_is_listed():
    report = score([result("a", {"issue_date": "2026-01-01"}, {"issue_date": "2026-01-02"})])
    field = report["per_field"]["issue_date"]
    assert (field["tp"], field["fp"], field["fn"]) == (0, 1, 0)
    assert field["wrong_value"] == 1
    assert report["wrong_values"] == [
        {"case_id": "a", "field": "issue_date", "expected": "2026-01-01", "extracted": "2026-01-02"}
    ]


def test_spurious_field_is_reported_for_a_negative_case():
    report = score([result("neg", {}, {"institution_name": "Invented College"})])
    assert report["negative_cases"] == 1
    assert report["negative_false_positives"] == ["neg"]
    assert report["negative_false_positive_count"] == 1
    assert report["per_field"]["institution_name"]["fp"] == 1


def test_precision_and_recall_are_computed_from_the_confusion_matrix():
    results = [
        result("1", {"institution_name": "A"}, {"institution_name": "A"}),  # tp
        result("2", {"institution_name": "B"}, {}),  # fn
        result("3", {}, {"institution_name": "C"}),  # fp
        result("4", {"institution_name": "D"}, {}),  # fn
    ]
    report = score(results)
    field = report["per_field"]["institution_name"]
    assert (field["tp"], field["fp"], field["fn"]) == (1, 1, 2)
    assert field["precision"] == pytest.approx(0.5)
    assert field["recall"] == pytest.approx(1 / 3, abs=1e-4)
    assert field["f1"] == pytest.approx(0.4, abs=1e-4)


def test_micro_averages_across_fields_rather_than_per_case():
    results = [
        result("1", {"institution_name": "A", "issue_date": "2026-01-01"},
               {"institution_name": "A"}),
    ]
    report = score(results)
    assert report["micro"]["tp"] == 1
    assert report["micro"]["fn"] == 1
    assert report["micro"]["precision"] == 1.0
    assert report["micro"]["recall"] == 0.5


def test_a_raising_case_is_counted_as_a_failure_not_skipped():
    case = {
        "case_id": "boom",
        "category": "limit",
        "text": "x" * 100_001,  # over MAX_OCR_TEXT_CHARS: extraction raises
        "expected": {"institution_name": "A"},
    }
    outcome = evaluate_case(case)
    assert outcome.error is not None and "ValueError" in outcome.error
    assert outcome.extracted == {}
    assert not outcome.exact_match
    report = score([outcome])
    assert report["errors"][0]["case_id"] == "boom"
    assert report["per_field"]["institution_name"]["fn"] == 1


# --- corpus integrity -----------------------------------------------------


def test_corpus_is_loadable_and_large_enough():
    cases = load_corpus()
    assert len(cases) >= 40, "the corpus is meant to cover meaningful variation"
    ids = [case["case_id"] for case in cases]
    assert len(ids) == len(set(ids))


def test_corpus_covers_the_documented_field_set_and_negative_cases():
    cases = load_corpus()
    covered = {name for case in cases for name in case["expected"]}
    assert covered == TEXT_FIELDS
    negatives = [case for case in cases if not case["expected"] and not case.get("known_gap")]
    assert len(negatives) >= 15, "negative cases must be a real part of the corpus"


def test_corpus_categories_include_the_hard_scenarios():
    categories = {case.get("category") for case in load_corpus()}
    for required in {
        "clean-label-en",
        "clean-label-hi",
        "ambiguous-date",
        "invalid-date",
        "ocr-corruption",
        "noise",
        "duplicate-labels",
        "boundary",
        "personal-data",
        "multi-field",
    }:
        assert required in categories, f"missing corpus category {required}"


def test_corpus_contains_no_real_or_personal_data():
    text = CORPUS_PATH.read_text(encoding="utf-8")
    # Synthetic markers only; nothing that looks like a real identifier.
    assert "Example" in text
    for marker in ("@", "http://", "https://", "Aadhaar", "aadhaar", "PAN "):
        assert marker not in text, f"corpus must not contain {marker!r}"


def test_scored_cases_pass_and_known_gaps_are_reported_as_failing():
    report = run()
    assert report["errors"] == [], "no scored case may raise"
    assert report["negative_false_positive_count"] == 0
    assert report["exact_match_count"] == report["cases"]
    assert report["known_gaps"], "known defects must stay documented"
    assert all(gap["still_failing"] for gap in report["known_gaps"]), (
        "a known gap that now passes should have its known_gap flag removed"
    )
    assert all(gap["note"] for gap in report["known_gaps"])


# --- honesty --------------------------------------------------------------


def test_banner_warns_that_the_numbers_are_not_real_world_accuracy():
    for phrase in ("SYNTHETIC", "NOT A REAL-WORLD BENCHMARK", "not OCR accuracy"):
        assert phrase in BANNER
    assert BANNER in run()["banner"]


def test_cli_prints_the_banner_and_a_summary():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "synthetic corpus" in completed.stdout
    assert "known gaps" in completed.stdout


def test_cli_json_output_is_machine_readable(tmp_path: Path):
    output = tmp_path / "report.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", str(output), "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["cases"] >= 40
    assert "micro" in report and "per_field" in report and "known_gaps" in report


def test_check_mode_fails_when_a_negative_case_extracts_something(tmp_path: Path):
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text(
        json.dumps(
            {
                "case_id": "neg-spurious",
                "category": "noise",
                # A real label, but the case is labelled as expecting nothing.
                "text": "Institution Name: Unexpected College",
                "expected": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(corpus), "--check", "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "must leave unresolved values unresolved" in completed.stderr


def test_load_corpus_rejects_duplicate_ids(tmp_path: Path):
    corpus = tmp_path / "dup.jsonl"
    line = json.dumps({"case_id": "same", "text": "x", "expected": {}})
    corpus.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_corpus(corpus)

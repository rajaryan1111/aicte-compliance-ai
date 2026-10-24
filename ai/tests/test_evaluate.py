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
import unicodedata
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
    run_corpora,
    score,
    _print_human as print_human,
)

SCRIPT = REPO_ROOT / "ai" / "evaluate_extraction.py"
CORRUPTION_CORPUS_PATH = REPO_ROOT / "ai" / "corpus" / "ocr_corruption_cases.jsonl"
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


def test_corruption_slice_is_labelled_and_keeps_negative_cases():
    cases = load_corpus(CORRUPTION_CORPUS_PATH)
    assert len(cases) == 30
    assert {
        "ocr-inserted-newline",
        "ocr-misread-label",
        "ocr-latin-hindi-mix",
        "ocr-column-order",
    } <= {case["category"] for case in cases}
    negatives = [case for case in cases if not case["expected"] and not case.get("known_gap")]
    assert len(negatives) == 7
    assert len(negatives) >= len(cases) // 4
    assert len([c for c in cases if c.get("known_gap")]) == 15
    # Unicode decomposition must be present explicitly, not by accident of encoding.
    decomposed = [case for case in cases if case["case_id"] == "CLH-007"]
    assert all(unicodedata.normalize("NFC", case["text"]) != case["text"] for case in decomposed)


def test_multiple_corpora_are_scored_as_separate_slices():
    reports = run_corpora([CORPUS_PATH, CORRUPTION_CORPUS_PATH])

    assert [report["corpus"] for report in reports] == [
        str(CORPUS_PATH.resolve().relative_to(REPO_ROOT)),
        str(CORRUPTION_CORPUS_PATH.resolve().relative_to(REPO_ROOT)),
    ]
    # 56 scored: BND-002 and HI-005 migrated out of known-gap status once the
    # backend fix landed (merge of origin/main, commit eec3a81).
    assert [report["cases"] for report in reports] == [56, 15]
    assert [report["exact_match_count"] for report in reports] == [56, 15]
    assert reports[0]["negative_false_positive_count"] == 0
    assert reports[1]["negative_false_positive_count"] == 0
    assert len(reports[1]["known_gaps"]) == 15


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
    if report["known_gaps"]:
        assert all(gap["still_failing"] for gap in report["known_gaps"]), (
            "a known gap that now passes should have its known_gap flag removed"
        )
        assert all(gap["note"] for gap in report["known_gaps"])


def test_fixed_ocr_gaps_bnd002_and_hi005_remain_resolved():
    cases = {c["case_id"]: evaluate_case(c) for c in load_corpus() if c["case_id"] in ("BND-002", "HI-005")}
    assert cases["BND-002"].exact_match, "BND-002 must not extract sub-3-character institution name"
    assert cases["BND-002"].extracted == {}
    assert cases["HI-005"].exact_match, "HI-005 must extract 'शैक्षणिक सत्र' session"
    assert cases["HI-005"].extracted == {"academic_year": "2026-2027"}


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


def test_cli_reports_repeated_corpora_without_merging_them(tmp_path: Path):
    output = tmp_path / "reports.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus",
            str(CORPUS_PATH),
            "--corpus",
            str(CORRUPTION_CORPUS_PATH),
            "--json",
            str(output),
            "--quiet",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(report["corpora"]) == 2
    assert [slice_report["cases"] for slice_report in report["corpora"]] == [56, 15]
    assert completed.stdout.count("synthetic corpus") == 2


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


def test_check_mode_fails_when_a_scored_case_mismatches(tmp_path: Path):
    corpus = tmp_path / "mismatch.jsonl"
    corpus.write_text(
        json.dumps(
            {
                "case_id": "positive-mismatch",
                "category": "clean-label-en",
                "text": "Issue Date: 2026-04-30",
                "expected": {"issue_date": "2027-04-30"},
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
    assert "scored cases did not match exactly" in completed.stderr


def test_load_corpus_rejects_duplicate_ids(tmp_path: Path):
    corpus = tmp_path / "dup.jsonl"
    line = json.dumps({"case_id": "same", "text": "x", "expected": {}})
    corpus.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_corpus(corpus)


# --- invalid input, report handling and determinism -----------------------


@pytest.mark.parametrize(
    ("payload", "name", "message"),
    [
        # A corpus that does not exist must fail loudly, not return zero cases.
        (None, "absent.jsonl", "corpus not found"),
        # Malformed JSONL must report the offending line.
        ('{"case_id": "x", "text": "unterminated string\n', "broken.jsonl", "line 1"),
        # Whitespace-only corpora are rejected rather than scoring an empty set.
        ("\n\n", "empty.jsonl", "is empty"),
        # A case without the required expected map is a schema error.
        (
            json.dumps({"case_id": "a", "text": "x"}) + "\n",
            "missing-field.jsonl",
            "missing 'expected'",
        ),
        # expected must be an object, not a list of field names.
        (
            json.dumps({"case_id": "a", "text": "x", "expected": ["institution_name"]})
            + "\n",
            "wrong-type.jsonl",
            "expected must be an object",
        ),
    ],
)
def test_cli_exits_nonzero_with_a_clear_error_on_invalid_input(
    tmp_path: Path, payload: str | None, name: str, message: str
):
    path = tmp_path / name
    if payload is not None:
        path.write_text(payload, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(path), "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert message in completed.stderr


def test_cli_json_report_replaces_any_previous_report(tmp_path: Path):
    """A new run must fully replace a report file, never merge with stale data."""
    output = tmp_path / "report.json"
    output.write_text('{"stale": true}\n', encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", str(output), "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "stale" not in payload
    assert "cases" in payload and "micro" in payload and "known_gaps" in payload


def test_cli_output_is_deterministic_across_runs(tmp_path: Path):
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    runs = [
        subprocess.run(
            [sys.executable, str(SCRIPT), "--json", str(target), "--quiet"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        for target in (first, second)
    ]
    for completed in runs:
        assert completed.returncode == 0, completed.stderr
    assert runs[0].stdout == runs[1].stdout
    assert first.read_bytes() == second.read_bytes()


def test_human_report_shows_an_extraction_error_inside_a_known_gap(capsys):
    """A raising gap case must not look like an ordinary mismatch in human output."""
    report = {
        "corpus": "synthetic",
        "cases": 1,
        "exact_match_count": 0,
        "exact_match_rate": 0.0,
        "per_field": {},
        "micro": {"tp": 0, "fp": 0, "fn": 0, "wrong_value": 0,
                  "precision": 0.0, "recall": 0.0, "f1": 0.0},
        "negative_cases": 0,
        "negative_false_positives": [],
        "negative_false_positive_count": 0,
        "wrong_values": [],
        "errors": [],
        "known_gaps": [{
            "case_id": "GAP-RAISE-001",
            "category": "ocr-misread-label",
            "expected": {},
            "extracted": {},
            "exact_match": False,
            "known_gap": True,
            "error": "ValueError: OCR text exceeds the 100000-character processing limit",
            "still_failing": True,
            "note": "a gap that raises",
        }],
    }
    print_human(report, show_banner=False)
    out = capsys.readouterr().out
    assert "GAP-RAISE-001: STILL FAILING" in out
    assert "extraction raised: ValueError" in out
    assert "a gap that raises" in out


def test_check_mode_tolerates_errors_inside_documented_known_gaps(tmp_path: Path):
    """Only scored cases may fail --check; documented gaps stay exempt."""
    corpus = tmp_path / "gap-raise.jsonl"
    corpus.write_text(
        json.dumps(
            {
                "case_id": "GAP-RAISE-002",
                "category": "ocr-misread-label",
                "known_gap": True,
                "notes": "a deliberate gap that raises during extraction",
                "text": "x" * 100_001,
                "expected": {"institution_name": "Example Technical Institute"},
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
    assert completed.returncode == 0, completed.stderr


# --- report hardening: fingerprint, coverage, per-case results -------------


def test_report_records_corpus_fingerprint_and_category_coverage():
    import hashlib

    report = run(CORRUPTION_CORPUS_PATH)
    assert report["corpus_sha256"] == hashlib.sha256(
        CORRUPTION_CORPUS_PATH.read_bytes()
    ).hexdigest()
    coverage = report["by_category"]["ocr-misread-label"]
    assert coverage == {"cases": 2, "exact_match_count": 2, "failing_cases": []}
    ids = [case["case_id"] for case in report["case_results"]]
    assert len(ids) == report["cases"] == len(set(ids))


def test_case_results_agree_with_the_report_metrics():
    report = run(CORRUPTION_CORPUS_PATH)
    exact = sum(1 for case in report["case_results"] if case["exact_match"])
    assert exact == report["exact_match_count"]
    gap_ids = {gap["case_id"] for gap in report["known_gaps"]}
    scored_ids = {case["case_id"] for case in report["case_results"]}
    assert gap_ids.isdisjoint(scored_ids)
    for case in report["case_results"]:
        if case["exact_match"]:
            assert case["error"] is None and case["extracted"] == case["expected"]


# --- baseline comparison ---------------------------------------------------


def test_compare_is_quiet_for_identical_runs_and_never_touches_the_baseline(tmp_path: Path):
    baseline = tmp_path / "base.json"
    current = tmp_path / "current.json"
    for output in (baseline, current):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--json", str(output), "--quiet"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )
        assert completed.returncode == 0, completed.stderr
    untouched = baseline.read_bytes()
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--compare", str(baseline), "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0
    assert "NEW REGRESSIONS" not in completed.stdout
    assert baseline.read_bytes() == untouched


def test_compare_flags_a_newly_failing_case_and_fails_the_run(tmp_path: Path):
    corpus = tmp_path / "mini.jsonl"
    stable = json.dumps({"case_id": "M-001", "category": "clean-label-en",
                         "text": "Institution Name: Example College",
                         "expected": {"institution_name": "Example College"}})
    tightened = json.dumps({"case_id": "M-001", "category": "clean-label-en",
                            "text": "Institution Name: Example College",
                            "expected": {"institution_name": "Different College"}})
    corpus.write_text(stable + "\n", encoding="utf-8")
    baseline = tmp_path / "base.json"
    first = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(corpus), "--json", str(baseline),
         "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert first.returncode == 0, first.stderr
    corpus.write_text(tightened + "\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(corpus),
         "--compare", str(baseline), "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 1
    assert "NEW REGRESSIONS" in completed.stdout
    assert "M-001" in completed.stdout
    assert "corpus bytes changed" in completed.stdout
    assert "nothing compared" not in completed.stdout


def test_compare_reports_a_corpus_missing_from_the_baseline(tmp_path: Path):
    corpus = tmp_path / "elsewhere.jsonl"
    corpus.write_text(
        json.dumps({"case_id": "M-001", "category": "clean-label-en",
                    "text": "Institution Name: Example College",
                    "expected": {"institution_name": "Example College"}}) + "\n",
        encoding="utf-8",
    )
    # A real baseline that covers neither corpus the current run uses.
    other = tmp_path / "unrelated-corpus.json"
    unrelated = tmp_path / "unrelated-corpus.jsonl"
    unrelated.write_text(
        json.dumps({"case_id": "U-001", "category": "clean-label-en",
                    "text": "Institution Name: Other College",
                    "expected": {"institution_name": "Other College"}}) + "\n",
        encoding="utf-8",
    )
    seeded = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(unrelated),
         "--json", str(other), "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert seeded.returncode == 0, seeded.stderr
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(corpus),
         "--compare", str(other), "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0
    assert "no matching corpus in the baseline" in completed.stdout


@pytest.mark.parametrize(
    ("content", "message"),
    [(None, "baseline not found"), ("{}", "baseline does not look like an evaluator report")],
)
def test_compare_rejects_missing_or_invalid_baseline_files(
    tmp_path: Path, content: str | None, message: str
):
    corpus = tmp_path / "mini.jsonl"
    corpus.write_text(
        json.dumps({"case_id": "M-001", "category": "clean-label-en",
                    "text": "Institution Name: Example College",
                    "expected": {"institution_name": "Example College"}}) + "\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    if content is not None:
        baseline.write_text(content, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(corpus),
         "--compare", str(baseline), "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 1
    assert message in completed.stderr


def test_compare_matches_both_slices_of_a_multi_corpus_run(tmp_path: Path):
    baseline = tmp_path / "multi.json"
    first = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", str(baseline), "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert first.returncode == 0, first.stderr
    completed = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--compare", str(baseline), "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "no matching corpus" not in completed.stdout
    assert "NEW REGRESSIONS" not in completed.stdout
# --- engine selection (labelled bake-off) and confidence passthrough -------

def test_run_records_the_engine_label():
    from ai.evaluate_extraction import DEFAULT_ENGINE_LABEL

    assert run()["engine"] == DEFAULT_ENGINE_LABEL
    assert (
        run(CORRUPTION_CORPUS_PATH, engine="stub:engine")["engine"] == "stub:engine"
    )


def test_evaluate_case_accepts_plain_value_and_provenance_engines():
    class Field:
        def __init__(self, value: str | None, confidence: float | None = None):
            self.value, self.confidence = value, confidence

    case = {
        "case_id": "C-1",
        "text": "text",
        "expected": {"institution_name": "X"},
    }
    provenance = evaluate_case(case, lambda _t: {"institution_name": Field("X", 0.42)})
    assert provenance.exact_match
    assert provenance.as_dict()["confidences"] == {"institution_name": 0.42}

    plain = evaluate_case(case, lambda _t: {"institution_name": "X"})
    assert plain.exact_match and "confidences" not in plain.as_dict()

    none_value = evaluate_case(case, lambda _t: {"institution_name": Field(None)})
    assert none_value.extracted == {} and not none_value.exact_match


def test_cli_engine_flag_runs_a_bake_off_and_keeps_check_semantics(tmp_path: Path):
    import os

    (tmp_path / "stub_engine.py").write_text(
        "def extract_nothing(text):\n    return {}\n", encoding="utf-8"
    )
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    json_out = tmp_path / "stub.json"

    with_check = subprocess.run(
        [
            sys.executable,
            "ai/evaluate_extraction.py",
            "--corpus",
            str(CORRUPTION_CORPUS_PATH),
            "--engine",
            "stub_engine:extract_nothing",
            "--check",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert with_check.returncode == 1  # a dead engine fails every scored case
    assert "engine: stub_engine:extract_nothing" in with_check.stdout

    json_report = subprocess.run(
        [
            sys.executable,
            "ai/evaluate_extraction.py",
            "--corpus",
            str(CORRUPTION_CORPUS_PATH),
            "--engine",
            "stub_engine:extract_nothing",
            "--json",
            str(json_out),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert json_report.returncode == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["engine"] == "stub_engine:extract_nothing"
    assert payload["exact_match_count"] == 7  # the negative cases still pass


def test_cli_rejects_invalid_engine_specs():
    for spec in (
        "malformed",
        "no_such_module:attr",
        "backend.app.ocr_pipeline:definitely_not_an_engine",
    ):
        completed = subprocess.run(
            [
                sys.executable,
                "ai/evaluate_extraction.py",
                "--corpus",
                str(CORRUPTION_CORPUS_PATH),
                "--engine",
                spec,
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert completed.returncode == 1
        assert "error:" in completed.stderr


# --- preprocessing / normalization diagnostics ------------------------------

def test_normalize_removes_invisible_noise_with_provenance():
    from ai.normalize import normalize_text

    text = "Institution\u200b Name: No\u00ad  \r\nX\u2028Y  \n"
    payload, changes = normalize_text(text)
    assert "\u200b" not in payload and "\u00ad" not in payload and "\u2028" not in payload
    assert "\r" not in payload
    rules = {c["rule"] for c in changes}
    assert {"remove-invisible-chars", "line-separator-to-lf"} <= rules
    invisible = next(c for c in changes if c["rule"] == "remove-invisible-chars")
    assert invisible["instances"] == 2  # zero-width space and soft hyphen
    assert any("U+200B" in example for example in invisible["examples"])


def test_normalize_nfkc_composes_allocated_forms_only_when_needed():
    from ai.normalize import normalize_text

    nfd = unicodedata.normalize("NFD", "Caf\u00e9: 2026")
    payload, changes = normalize_text(nfd)
    assert payload == "Caf\u00e9: 2026"
    assert [c["rule"] for c in changes] == ["nfkc"]

    clean = "Institution Name: Example College"
    payload_clean, changes_clean = normalize_text(clean)
    assert payload_clean == clean and changes_clean == []


def test_normalize_is_idempotent_and_preserves_meaningful_text():
    from ai.normalize import normalize_text

    messy = "  \u200bA\u2028B\r\n\tC  \n\n\n\nD\u200b \n"
    once, changes_once = normalize_text(messy)
    twice, changes_twice = normalize_text(once)
    assert twice == once and changes_twice == []

    meaningful = "शैक्षणिक सत्र: 2026/2027 — Certificate No; CERT/2026/0099"
    assert normalize_text(meaningful) == (meaningful, [])


def test_preprocessing_diagnosis_matches_measured_evidence_only():
    from ai.evaluate_extraction import load_corpus, preprocessing_diagnosis

    cases = load_corpus(CORRUPTION_CORPUS_PATH)
    gap_ids = {c["case_id"] for c in cases if c.get("known_gap")}
    diagnosis = preprocessing_diagnosis(cases)
    assert set(diagnosis["repaired"]) == {"CMIS-009"}
    assert diagnosis["repaired"]["CMIS-009"] == ["remove-invisible-chars"]
    assert "CNL-001" in diagnosis["not_fixed_by_these_rules"]
    assert (
        set(diagnosis["repaired"]) | set(diagnosis["not_fixed_by_these_rules"])
    ) <= gap_ids
    assert diagnosis["extraction_raised"] == []


def test_preprocessing_diagnosis_records_raising_engines_without_stopping():
    from ai.evaluate_extraction import preprocessing_diagnosis

    cases = [
        {"case_id": "R-1", "known_gap": True, "text": "text", "expected": {}},
        {
            "case_id": "R-2",
            "known_gap": True,
            "text": "Institution\u200b Name: X",
            "expected": {"institution_name": "X"},
        },
    ]

    def raising_engine(_text: str):
        raise RuntimeError("engine down")

    diagnosis = preprocessing_diagnosis(cases, raising_engine)
    assert diagnosis["extraction_raised"] == ["R-1", "R-2"]  # both raise; none masked
    assert diagnosis["repaired"] == {}  # a dead engine repairs nothing


def test_cli_normalize_flag_prints_diagnosis_and_keeps_exit_codes():
    with_check = subprocess.run(
        [
            sys.executable,
            "ai/evaluate_extraction.py",
            "--corpus",
            str(CORRUPTION_CORPUS_PATH),
            "--normalize",
            "--check",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert with_check.returncode == 0
    assert "preprocessing diagnosis" in with_check.stdout
    assert "1/15 known-gap cases" in with_check.stdout
    assert "CNL-001" in with_check.stdout  # not fixed; stays visible
    assert "remove-invisible-chars" in with_check.stdout
    assert "backend-owned change" in with_check.stdout


def test_cli_normalize_is_deterministic_and_run_independently():
    runs = [
        subprocess.run(
            [
                sys.executable,
                "ai/evaluate_extraction.py",
                "--corpus",
                str(CORRUPTION_CORPUS_PATH),
                "--normalize",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        for _ in range(2)
    ]
    assert runs[0].returncode == runs[1].returncode == 0
    assert runs[0].stdout == runs[1].stdout


# --- remaining schema rules, metric edges, baseline exit-code policy -------

@pytest.mark.parametrize(
    ("line", "message"),
    [
        ('[1, 2]', "record must be a JSON object, got list"),
        ('{"case_id": "", "text": "t", "expected": {}}',
         "case_id must be a non-empty string"),
        ('{"case_id": 3, "text": "t", "expected": {}}',
         "case_id must be a non-empty string"),
        ('{"case_id": "a", "text": 7, "expected": {}}', "text must be a string"),
        ('{"case_id": "a", "text": "t", "expected": {"": "x"}}',
         "field names must be non-empty strings"),
        ('{"case_id": "a", "text": "t", "expected": {"institution_name": 9}}',
         "must be a string"),
        ('{"case_id": "a", "text": "t", "expected": {}, "notes": 5}',
         "notes must be a string"),
        ('{"case_id": "a", "text": "t", "expected": {}, "known_gap": "yes"}',
         "known_gap must be a boolean"),
    ],
)
def test_cli_surface_for_remaining_corpus_schema_rules(
    tmp_path: Path, line: str, message: str
):
    corpus = tmp_path / "schema.jsonl"
    corpus.write_text(line + "\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(corpus), "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert message in completed.stderr


def test_cli_rejects_a_corpus_that_is_not_valid_utf8(tmp_path: Path):
    corpus = tmp_path / "bad-encoding.jsonl"
    corpus.write_bytes(b'{"case_id": "\xff", "text": "t", "expected": {}}\n')
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(corpus), "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "not valid UTF-8" in completed.stderr


def test_hand_worked_metric_example_settles_every_counter():
    """tp=2, fp=3, fn=1 gives precision 0.4, recall 2/3 and F1 0.5 exactly."""
    from ai.evaluate_extraction import CaseResult, score

    results = [
        CaseResult(
            case_id="R1", category="clean",
            expected={"institution_name": "A", "valid_until": "2027-01-01"},
            extracted={"institution_name": "A", "valid_until": "2027-01-01"},
            known_gap=False,
        ),
        CaseResult(
            case_id="R2", category="clean",
            expected={"institution_name": "B", "issue_date": "2026-01-01"},
            extracted={"institution_name": "C"},
            known_gap=False,
        ),
        # A negative case must keep spurious extraction visible.
        CaseResult(
            case_id="R3", category="clean", expected={},
            extracted={"issue_date": "x"}, known_gap=False,
        ),
    ]
    report = score(results)
    # tp=2, fp=2, fn=1: precision 0.5, recall 2/3, F1 2*(0.5*2/3)/(0.5+2/3)=4/7.
    assert report["micro"] == {
        "tp": 2, "fp": 2, "fn": 1, "wrong_value": 0,
        "precision": 0.5, "recall": 0.6667, "f1": 0.5714,
    }
    assert report["exact_match_count"] == 1
    assert report["exact_match_rate"] == round(1 / 3, 4)
    assert report["negative_cases"] == 1
    assert report["negative_false_positives"] == ["R3"]
    assert report["negative_false_positive_count"] == 1
    assert {w["case_id"] for w in report["wrong_values"]} == {"R2", "R3"}
    # Wrong-value detail is kept per case; the aggregate wrong-value counter of
    # the micro roll-up is not merged into it (they are different definitions).
    assert report["per_field"]["institution_name"]["wrong_value"] == 1
    assert report["per_field"]["issue_date"]["fp"] == 1


def test_score_on_empty_input_and_zero_denominators():
    from ai.evaluate_extraction import FieldScore, score

    report = score([])
    assert report["cases"] == 0
    assert report["exact_match_count"] == 0
    assert report["exact_match_rate"] == 0.0
    assert report["micro"]["precision"] == report["micro"]["recall"] == 0.0
    assert report["micro"]["f1"] == 0.0
    assert report["negative_cases"] == 0
    # Denominator-zero properties are reported as 0.0, never divide by zero.
    assert FieldScore().precision == FieldScore().recall == FieldScore().f1 == 0.0


def _cli_cap(corpus: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--corpus", str(corpus), *extra, "--quiet"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )


def test_compare_notifies_when_a_passing_case_becomes_a_known_gap(tmp_path: Path):
    corpus = tmp_path / "flip.jsonl"
    scored_first = json.dumps({
        "case_id": "FL-1", "category": "edge",
        "text": "Institution Name: Alpha College",
        "expected": {"institution_name": "Alpha College"},
    })
    gap_after = json.dumps({
        "case_id": "FL-1", "category": "edge", "known_gap": True,
        "text": "Institution Name: Alpha College",
        "expected": {"institution_name": "Alpha College"},
    })
    corpus.write_text(scored_first + "\n", encoding="utf-8")
    baseline = tmp_path / "base.json"
    assert _cli_cap(corpus, "--json", str(baseline)).returncode == 0
    corpus.write_text(gap_after + "\n", encoding="utf-8")
    completed = _cli_cap(corpus, "--compare", str(baseline))
    # A rescoped case left the scored denominator by flag: clearly noted, not
    # counted as a scored regression, and the run is not silently gated.
    assert completed.returncode == 0
    assert "scored case FL-1 absent from the current run" in completed.stdout
    assert "new documented known gap FL-1" in completed.stdout


def test_compare_notifies_when_a_known_gap_becomes_a_scored_failure(tmp_path: Path):
    corpus = tmp_path / "flip.jsonl"
    gap_first = json.dumps({
        "case_id": "FL-2", "category": "edge", "known_gap": True,
        "text": "Institution Name: Gamma College, Valid Until: 2099-01-01",
        "expected": {"institution_name": "Gamma College", "valid_until": "2099-01-01"},
    })
    # The case is unflagged with an intentionally failing expected value.
    failing_after = json.dumps({
        "case_id": "FL-2", "category": "edge",
        "text": "Institution Name: Gamma College, Valid Until: 2099-01-01",
        "expected": {"institution_name": "Gamma College", "valid_until": "2030-01-01"},
    })
    corpus.write_text(gap_first + "\n", encoding="utf-8")
    baseline = tmp_path / "base.json"
    assert _cli_cap(corpus, "--json", str(baseline)).returncode == 0
    corpus.write_text(failing_after + "\n", encoding="utf-8")
    completed = _cli_cap(corpus, "--compare", str(baseline))
    # The same truth: no baseline scored success exists to regress; the flag
    # change and the failure are visible, and the run exits 0.
    assert completed.returncode == 0
    assert "new scored case FL-2 has no baseline result" in completed.stdout
    assert "documented known gap FL-2 no longer exists in the corpus" in completed.stdout
    assert "micro F1" in completed.stdout


def test_compare_notes_a_brand_new_case_that_fails_with_exit_zero(tmp_path: Path):
    corpus = tmp_path / "growth.jsonl"
    base = json.dumps({
        "case_id": "G-1", "category": "clean-label-en",
        "text": "Institution Name: Alpha College",
        "expected": {"institution_name": "Alpha College"},
    })
    added = json.dumps({
        "case_id": "G-2", "category": "clean-label-en",
        "text": "Institution Name: Alpha College",
        "expected": {"institution_name": "Wrong College"},
    })
    corpus.write_text(base + "\n", encoding="utf-8")
    baseline = tmp_path / "base.json"
    assert _cli_cap(corpus, "--json", str(baseline)).returncode == 0
    corpus.write_text(base + "\n" + added + "\n", encoding="utf-8")
    completed = _cli_cap(corpus, "--compare", str(baseline))
    assert completed.returncode == 0
    assert "new scored case G-2 has no baseline result" in completed.stdout
    assert "NEW REGRESSIONS" not in completed.stdout


def test_compare_fails_when_a_negative_case_starts_pulling_fields(tmp_path: Path):
    corpus = tmp_path / "negative.jsonl"
    clean = json.dumps({
        "case_id": "N-1", "category": "clean-label-en",
        "text": "The rain in Spain stays mainly", "expected": {},
    })
    leaking = json.dumps({
        "case_id": "N-1", "category": "clean-label-en",
        "text": "Institution Name: Chance College", "expected": {},
    })
    corpus.write_text(clean + "\n", encoding="utf-8")
    baseline = tmp_path / "base.json"
    assert _cli_cap(corpus, "--json", str(baseline)).returncode == 0
    corpus.write_text(leaking + "\n", encoding="utf-8")
    completed = _cli_cap(corpus, "--compare", str(baseline))
    assert completed.returncode == 1
    assert "NEW REGRESSIONS" in completed.stdout
    assert "N-1" in completed.stdout


def test_compare_refuses_an_ambiguous_same_name_baseline(tmp_path: Path):
    """Two baseline slices with one basename must never be matched silently."""
    def cap(target_corpus: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--corpus", str(target_corpus), *extra,
             "--quiet"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )

    slice_a = tmp_path / "aa"
    slice_b = tmp_path / "bb"
    slice_a.mkdir()
    slice_b.mkdir()
    corpus_a = slice_a / "shared.jsonl"
    corpus_b = slice_b / "shared.jsonl"
    corpus_a.write_text(json.dumps({
        "case_id": "A-1", "category": "clean-label-en",
        "text": "Institution Name: Alpha College",
        "expected": {"institution_name": "Alpha College"},
    }) + "\n", encoding="utf-8")
    corpus_b.write_text(json.dumps({
        "case_id": "B-1", "category": "clean-label-en",
        "text": "Valid Until: 2099-01-01",
        "expected": {"valid_until": "2099-01-01"},
    }) + "\n", encoding="utf-8")
    report_a = tmp_path / "a.json"
    report_b = tmp_path / "b.json"
    assert cap(corpus_a, "--json", str(report_a)).returncode == 0
    assert cap(corpus_b, "--json", str(report_b)).returncode == 0
    merged = {"corpora": [
        json.loads(report_a.read_text(encoding="utf-8")),
        json.loads(report_b.read_text(encoding="utf-8")),
    ]}
    ambiguous = tmp_path / "ambiguous.json"
    ambiguous.write_text(json.dumps(merged), encoding="utf-8")
    elsewhere = slice_b / "renamed-shared.jsonl"
    corpus_b.rename(elsewhere)
    completed = cap(elsewhere, "--compare", str(ambiguous))
    assert completed.returncode == 0
    assert "no matching corpus in the baseline" in completed.stdout
    assert "NEW REGRESSIONS" not in completed.stdout
    # The ambiguity is resolved when the exact path is available again.
    elsewhere.rename(corpus_b)
    resolved = cap(corpus_b, "--compare", str(ambiguous))
    assert resolved.returncode == 0
    assert "no matching corpus in the baseline" not in resolved.stdout


def test_evaluation_doc_states_the_compare_exit_code_policy():
    text = (REPO_ROOT / "ai" / "EVALUATION.md").read_text(encoding="utf-8")
    for phrase in (
        "Exit-code policy for `--compare`",
        "scored success in the baseline now fails",
        "negative false positives now reports one",
        "visible note with exit 0",
        "no baseline result yet",
    ):
        assert phrase in text, phrase

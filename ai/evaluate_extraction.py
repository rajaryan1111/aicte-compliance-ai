#!/usr/bin/env python3
"""Score institutional-field extraction against a synthetic labelled corpus.

    python ai/evaluate_extraction.py              # human-readable report
    python ai/evaluate_extraction.py --json out.json
    python ai/evaluate_extraction.py --quiet      # numbers only, for CI

What it measures
----------------
For every case in ``ai/corpus/extraction_cases.jsonl`` the extractor
(``backend.app.ocr_pipeline.extract_institution_fields``, imported read-only) is run
on the labelled text and each expected field is compared exactly:

* **true positive** — field expected and extracted with the identical value
* **false positive** — field extracted that was not expected (or with a wrong value).
  For a case labelled ``{}`` (a negative case) *any* extracted field is a false positive
* **false negative** — field expected but not extracted

Precision, recall and F1 are reported per field and micro-averaged; exact-match rate is
reported per case. Nothing is dropped from a denominator: a case that raises is counted
as a failure, not skipped.

What it does not measure
------------------------
These sentences are synthetic. There is no scanner noise model, no real institutional
document, no Hindi evaluation set beyond label spelling, and no held-out split. The
numbers describe *this corpus only* and must never be quoted as real-world OCR accuracy.
Cases marked ``"known_gap": true`` are reported separately: they encode behaviour the
extractor is *known* to get wrong today, so they are not counted as passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "ai" / "corpus" / "extraction_cases.jsonl"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.ocr_pipeline import extract_institution_fields  # noqa: E402

BANNER = (
    "SYNTHETIC CORPUS — NOT A REAL-WORLD BENCHMARK. "
    "These numbers describe a hand-written synthetic corpus of label/date extraction "
    "cases. They are not OCR accuracy, are not measured on real documents, and must "
    "not be reported as a production or field-accuracy claim."
)


@dataclass
class FieldScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    wrong_value: int = 0

    @property
    def precision(self) -> float:
        denominator = self.tp + self.fp
        return self.tp / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.tp + self.fn
        return self.tp / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "wrong_value": self.wrong_value,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class CaseResult:
    case_id: str
    category: str
    expected: dict[str, str]
    extracted: dict[str, str]
    known_gap: bool
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def exact_match(self) -> bool:
        return self.error is None and self.extracted == self.expected

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "expected": self.expected,
            "extracted": self.extracted,
            "exact_match": self.exact_match,
            "known_gap": self.known_gap,
            "error": self.error,
            **self.extra,
        }


def load_corpus(path: Path = CORPUS_PATH) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"error: corpus not found: {path}")
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(f"error: {path.name} line {line_number}: {error}") from error
        for key in ("case_id", "text", "expected"):
            if key not in case:
                raise SystemExit(f"error: {path.name} line {line_number}: missing {key!r}")
        if not isinstance(case["expected"], dict):
            raise SystemExit(f"error: {path.name} line {line_number}: expected must be an object")
        cases.append(case)
    if not cases:
        raise SystemExit(f"error: {path.name} is empty")
    ids = [case["case_id"] for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise SystemExit(f"error: duplicate case ids: {duplicates}")
    return cases


def evaluate_case(case: dict[str, Any]) -> CaseResult:
    expected = dict(case["expected"])
    try:
        extracted = {
            name: field.value
            for name, field in extract_institution_fields(case["text"]).items()
        }
        error = None
    except Exception as exc:  # noqa: BLE001 - a raising case is a failure, not a skip
        extracted, error = {}, f"{type(exc).__name__}: {exc}"
    return CaseResult(
        case_id=case["case_id"],
        category=case.get("category", "uncategorised"),
        expected=expected,
        extracted=extracted,
        known_gap=bool(case.get("known_gap", False)),
        error=error,
    )


def score(results: list[CaseResult]) -> dict[str, Any]:
    per_field: dict[str, FieldScore] = defaultdict(FieldScore)
    wrong_values: list[dict[str, str]] = []

    for result in results:
        for name, expected_value in result.expected.items():
            score_field = per_field[name]
            actual_value = result.extracted.get(name)
            if actual_value == expected_value:
                score_field.tp += 1
            elif actual_value is None:
                score_field.fn += 1
            else:
                score_field.fp += 1
                score_field.wrong_value += 1
                wrong_values.append(
                    {"case_id": result.case_id, "field": name, "expected": expected_value,
                     "extracted": actual_value}
                )
        for name, actual_value in result.extracted.items():
            if name not in result.expected:
                per_field[name].fp += 1
                wrong_values.append(
                    {"case_id": result.case_id, "field": name, "expected": None,
                     "extracted": actual_value}
                )

    micro_tp = sum(score.tp for score in per_field.values())
    micro_fp = sum(score.fp for score in per_field.values())
    micro_fn = sum(score.fn for score in per_field.values())
    micro = FieldScore(tp=micro_tp, fp=micro_fp, fn=micro_fn)

    negative_cases = [r for r in results if not r.expected]
    negative_false_positives = [r.case_id for r in negative_cases if r.extracted]
    exact_matches = sum(1 for r in results if r.exact_match)

    return {
        "cases": len(results),
        "exact_match_count": exact_matches,
        "exact_match_rate": round(exact_matches / len(results), 4) if results else 0.0,
        "per_field": {name: s.as_dict() for name, s in sorted(per_field.items())},
        "micro": micro.as_dict(),
        "negative_cases": len(negative_cases),
        "negative_false_positives": negative_false_positives,
        "negative_false_positive_count": len(negative_false_positives),
        "wrong_values": wrong_values,
        "errors": [{"case_id": r.case_id, "error": r.error} for r in results if r.error],
    }


def run(corpus_path: Path = CORPUS_PATH) -> dict[str, Any]:
    cases = load_corpus(corpus_path)
    main_cases = [case for case in cases if not case.get("known_gap")]
    gap_cases = [case for case in cases if case.get("known_gap")]

    main_results = [evaluate_case(case) for case in main_cases]
    gap_results = [evaluate_case(case) for case in gap_cases]

    report = score(main_results)
    report["known_gaps"] = [
        {
            **result.as_dict(),
            "note": next(c.get("notes", "") for c in gap_cases if c["case_id"] == result.case_id),
            "still_failing": not result.exact_match,
        }
        for result in gap_results
    ]
    report["banner"] = BANNER
    try:
        report["corpus"] = str(corpus_path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        # --corpus may point outside the repository (tests, scratch experiments).
        report["corpus"] = str(corpus_path)
    return report


def _print_human(report: dict[str, Any]) -> None:
    print(BANNER)
    print()
    print(f"corpus: {report['corpus']}  ({report['cases']} scored cases, "
          f"{len(report['known_gaps'])} known gaps reported separately)")
    print()
    header = f"{'field':<22}{'tp':>4}{'fp':>4}{'fn':>4}{'precision':>11}{'recall':>9}{'f1':>7}"
    print(header)
    print("-" * len(header))
    for name, score in report["per_field"].items():
        print(
            f"{name:<22}{score['tp']:>4}{score['fp']:>4}{score['fn']:>4}"
            f"{score['precision']:>11.3f}{score['recall']:>9.3f}{score['f1']:>7.3f}"
        )
    micro = report["micro"]
    print("-" * len(header))
    print(
        f"{'micro (all fields)':<22}{micro['tp']:>4}{micro['fp']:>4}{micro['fn']:>4}"
        f"{micro['precision']:>11.3f}{micro['recall']:>9.3f}{micro['f1']:>7.3f}"
    )
    print()
    print(
        f"case exact-match: {report['exact_match_count']}/{report['cases']} "
        f"({report['exact_match_rate']:.1%})"
    )
    print(
        f"negative cases: {report['negative_cases']}, "
        f"with a spurious extraction: {report['negative_false_positive_count']}"
    )
    for case_id in report["negative_false_positives"]:
        print(f"  false positive: {case_id}")
    for wrong in report["wrong_values"][:10]:
        print(
            f"  wrong value: {wrong['case_id']} / {wrong['field']}: "
            f"expected {wrong['expected']!r}, got {wrong['extracted']!r}"
        )
    if report["errors"]:
        print("cases that raised (counted as failures):")
        for error in report["errors"]:
            print(f"  {error['case_id']}: {error['error']}")
    if report["known_gaps"]:
        print()
        print("known gaps (expected to fail until backend fixes them — not counted as passes):")
        for gap in report["known_gaps"]:
            status = "STILL FAILING" if gap["still_failing"] else "FIXED — remove the known_gap flag"
            print(f"  {gap['case_id']}: {status}")
            print(f"    {gap['note']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score synthetic OCR field extraction")
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    parser.add_argument("--json", type=Path, help="also write the full report as JSON here")
    parser.add_argument("--quiet", action="store_true", help="print one summary line only")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if a negative case produces a spurious extraction or a case raises",
    )
    args = parser.parse_args(argv)

    report = run(args.corpus)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.quiet:
        print(
            f"synthetic corpus: {report['cases']} cases, "
            f"exact-match {report['exact_match_count']}/{report['cases']}, "
            f"micro F1 {report['micro']['f1']:.3f}, "
            f"negative false positives {report['negative_false_positive_count']}, "
            f"known gaps {len(report['known_gaps'])}"
        )
    else:
        _print_human(report)

    if args.check:
        if report["errors"]:
            print("error: cases raised during extraction", file=sys.stderr)
            return 1
        if report["negative_false_positive_count"]:
            print(
                "error: negative cases produced spurious extractions; the extractor "
                "must leave unresolved values unresolved",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

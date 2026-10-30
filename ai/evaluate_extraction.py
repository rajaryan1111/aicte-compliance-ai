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
import hashlib
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import importlib

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "ai" / "corpus" / "extraction_cases.jsonl"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.ocr_pipeline import extract_institution_fields  # noqa: E402

DEFAULT_ENGINE = extract_institution_fields
DEFAULT_ENGINE_LABEL = "backend.app.ocr_pipeline:extract_institution_fields"

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
    """Load and strictly validate a corpus; every failure is a clean CLI exit 1.

    Documented rules (checked here and in ai/EVALUATION.md): each non-empty line
    is a JSON object; `case_id` is a unique non-empty string; `text` is a
    string; `expected` is an object of non-empty string field names with string
    values (negative cases use an empty object); `category` and `notes` are
    strings when present; `known_gap` is a boolean when present; the file must
    be valid UTF-8 and non-empty.
    """
    if not path.is_file():
        raise SystemExit(f"error: corpus not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit(f"error: {path.name} is not valid UTF-8: {error}") from error
    cases = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(f"error: {path.name} line {line_number}: {error}") from error
        if not isinstance(case, dict):
            type_name = type(case).__name__
            raise SystemExit(
                f"error: {path.name} line {line_number}: record must be a JSON object, got {type_name}"
            )
        for key in ("case_id", "text", "expected"):
            if key not in case:
                raise SystemExit(f"error: {path.name} line {line_number}: missing {key!r}")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise SystemExit(
                f"error: {path.name} line {line_number}: case_id must be a non-empty string"
            )
        if not isinstance(case["text"], str):
            raise SystemExit(f"error: {path.name} line {line_number}: text must be a string")
        expected = case["expected"]
        if not isinstance(expected, dict):
            raise SystemExit(f"error: {path.name} line {line_number}: expected must be an object")
        for field_name, value in expected.items():
            if not isinstance(field_name, str) or not field_name:
                raise SystemExit(
                    f"error: {path.name} line {line_number}: expected field names must be non-empty strings"
                )
            if not isinstance(value, str):
                raise SystemExit(
                    f"error: {path.name} line {line_number}: "
                    f"expected.{field_name!r} must be a string (negative cases use an empty object)"
                )
        for key in ("category", "notes"):
            if key in case and not isinstance(case[key], str):
                raise SystemExit(f"error: {path.name} line {line_number}: {key} must be a string")
        if "known_gap" in case and not isinstance(case["known_gap"], bool):
            raise SystemExit(f"error: {path.name} line {line_number}: known_gap must be a boolean")
        cases.append(case)
    if not cases:
        raise SystemExit(f"error: {path.name} is empty")
    ids = [case["case_id"] for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise SystemExit(f"error: duplicate case ids: {duplicates}")
    return cases


def _plain_value(field: Any) -> str | None:
    """Accept adapter engines that return OCRField-like objects or plain values."""
    value = getattr(field, "value", field)
    return None if value is None else str(value)


def evaluate_case(
    case: dict[str, Any], extractor: Callable[[str], dict[str, Any]] | None = None
) -> CaseResult:
    extractor = extractor or DEFAULT_ENGINE
    expected = dict(case["expected"])
    try:
        extracted, confidences = {}, {}
        for name, field in extractor(case["text"]).items():
            if (value := _plain_value(field)) is not None:
                extracted[name] = value
            if (confidence := getattr(field, "confidence", None)) is not None:
                confidences[name] = confidence
        error = None
        extra: dict[str, Any] = {"confidences": confidences} if confidences else {}
    except Exception as exc:  # noqa: BLE001 - a raising case is a failure, not a skip
        extracted, error, extra = {}, f"{type(exc).__name__}: {exc}", {}
    return CaseResult(
        case_id=case["case_id"],
        category=case.get("category", "uncategorised"),
        expected=expected,
        extracted=extracted,
        known_gap=bool(case.get("known_gap", False)),
        error=error,
        extra=extra,
    )


def score(results: list[CaseResult]) -> dict[str, Any]:
    per_field: dict[str, FieldScore] = defaultdict(FieldScore)
    wrong_values: list[dict[str, str | None]] = []

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


def category_summary(results: list[CaseResult]) -> dict[str, dict[str, Any]]:
    """Per-corruption-category coverage over the scored cases only."""
    summary: dict[str, dict[str, Any]] = {}
    for result in sorted(results, key=lambda r: (r.category, r.case_id)):
        entry = summary.setdefault(
            result.category, {"cases": 0, "exact_match_count": 0, "failing_cases": []}
        )
        entry["cases"] += 1
        if result.exact_match:
            entry["exact_match_count"] += 1
        else:
            entry["failing_cases"].append(result.case_id)
    return summary


def failure_reason(detail: dict[str, Any]) -> str:
    """One bounded line explaining why a scored case did not match."""
    if detail.get("error"):
        return f"raised {detail['error']}"
    expected, extracted = detail["expected"], detail["extracted"]
    diffs = [
        f"{name}: expected {value!r}, got {extracted.get(name)!r}"
        for name, value in expected.items()
        if extracted.get(name) != value
    ]
    diffs += [
        f"{name}: unexpected extraction {value!r}"
        for name, value in extracted.items()
        if name not in expected
    ]
    return "; ".join(diffs) or "case no longer matches its expected values"


def run(
    corpus_path: Path = CORPUS_PATH,
    extractor: Callable[[str], dict[str, Any]] | None = None,
    engine: str = DEFAULT_ENGINE_LABEL,
) -> dict[str, Any]:
    cases = load_corpus(corpus_path)
    main_cases = [case for case in cases if not case.get("known_gap")]
    gap_cases = [case for case in cases if case.get("known_gap")]

    main_results = [evaluate_case(case, extractor) for case in main_cases]
    gap_results = [evaluate_case(case, extractor) for case in gap_cases]

    report = score(main_results)
    report["engine"] = engine
    report["known_gaps"] = [
        {
            **result.as_dict(),
            "note": next(c.get("notes", "") for c in gap_cases if c["case_id"] == result.case_id),
            "still_failing": not result.exact_match,
        }
        for result in gap_results
    ]
    report["banner"] = BANNER
    report["by_category"] = category_summary(main_results)
    report["case_results"] = [result.as_dict() for result in main_results]
    try:
        report["corpus"] = str(corpus_path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        # --corpus may point outside the repository (tests, scratch experiments).
        report["corpus"] = str(corpus_path)
    report["corpus_sha256"] = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    return report


def _print_human(report: dict[str, Any], *, show_banner: bool = True) -> None:
    if show_banner:
        print(BANNER)
        print()
    print(f"corpus: {report['corpus']}  ({report['cases']} scored cases, "
          f"{len(report['known_gaps'])} known gaps reported separately)")
    print(f"engine: {report.get('engine', DEFAULT_ENGINE_LABEL)}")
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
    if report.get("corpus_sha256"):
        print(f"corpus fingerprint (sha256): {report['corpus_sha256']}")
    if report.get("by_category"):
        print("per covered category (scored cases only):")
        for category, coverage in report["by_category"].items():
            print(
                f"  {category}: {coverage['exact_match_count']}/{coverage['cases']} exact"
                + (
                    f" — failing: {', '.join(coverage['failing_cases'])}"
                    if coverage["failing_cases"]
                    else ""
                )
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
            if gap.get("error"):
                print(f"    extraction raised: {gap['error']}")
            print(f"    {gap['note']}")


def _normalise_baseline(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept either a single-corpus report or a multi-corpus {"corpora": [...]} file."""
    if "corpora" in payload:
        return list(payload["corpora"])
    if "cases" in payload and "micro" in payload:
        return [payload]
    raise ValueError("baseline does not look like an evaluator report")


def _match_baseline(
    report: dict[str, Any], baselines: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Match by corpus identity: exact path first, then file name (tmp compare runs)."""
    for candidate in baselines:
        if candidate.get("corpus") == report["corpus"]:
            return candidate
    name = report["corpus"].rsplit("/", 1)[-1]
    candidates = [
        candidate
        for candidate in baselines
        if str(candidate.get("corpus", "")).rsplit("/", 1)[-1] == name
    ]
    if len(candidates) == 1:
        return candidates[0]
    # An ambiguous filename (or no match): comparing the wrong report silently
    # would be worse than comparing none — the caller reports no match.
    return None


def compare_to_baseline(
    report: dict[str, Any], baseline: dict[str, Any] | None
) -> list[str]:
    """Human-readable, deterministic diff of a current report against a baseline.

    Returns the summary lines. Exit-code decisions belong to the caller; the
    baseline file is only ever read, never written or updated.
    """
    corpus = report["corpus"]
    if baseline is None:
        return [f"{corpus}: no matching corpus in the baseline; nothing compared"]
    lines: list[str] = []
    if baseline.get("corpus_sha256") != report.get("corpus_sha256"):
        lines.append(
            f"{corpus}: corpus bytes changed since the baseline (sha256 "
            f"{str(baseline.get('corpus_sha256'))[-12:]} ... -> "
            f"{str(report.get('corpus_sha256'))[-12:]} ...); case ids are still compared"
        )
    base_scored = {case["case_id"]: case for case in baseline.get("case_results", [])}
    current_scored = {case["case_id"]: case for case in report.get("case_results", [])}
    shared = sorted(set(base_scored) & set(current_scored))
    only_baseline = sorted(set(base_scored) - set(current_scored))
    only_current = sorted(set(current_scored) - set(base_scored))
    for case_id in only_baseline:
        lines.append(f"{corpus}: scored case {case_id} absent from the current run")
    for case_id in only_current:
        lines.append(f"{corpus}: new scored case {case_id} has no baseline result")

    regressions = [
        (case_id, failure_reason(current_scored[case_id]))
        for case_id in shared
        if base_scored[case_id]["exact_match"] and not current_scored[case_id]["exact_match"]
    ]
    fixed = [
        case_id
        for case_id in shared
        if not base_scored[case_id]["exact_match"] and current_scored[case_id]["exact_match"]
    ]
    if regressions:
        lines.append(f"{corpus}: NEW REGRESSIONS ({len(regressions)} scored case(s) now failing):")
        lines.extend(f"  {case_id}: {reason}" for case_id, reason in regressions)
    if fixed:
        lines.append(f"{corpus}: newly passing scored cases: {', '.join(fixed)}")

    base_gaps = {gap["case_id"]: gap for gap in baseline.get("known_gaps", [])}
    current_gaps = {gap["case_id"]: gap for gap in report.get("known_gaps", [])}
    for case_id in sorted(set(base_gaps) & set(current_gaps)):
        if base_gaps[case_id]["still_failing"] and not current_gaps[case_id]["still_failing"]:
            lines.append(
                f"{corpus}: known gap {case_id} now passes — remove the known_gap flag"
            )
        elif not base_gaps[case_id]["still_failing"] and current_gaps[case_id]["still_failing"]:
            lines.append(
                f"{corpus}: known gap {case_id} regressed from passing to failing"
            )
    for case_id in sorted(set(base_gaps) - set(current_gaps)):
        lines.append(f"{corpus}: documented known gap {case_id} no longer exists in the corpus")
    for case_id in sorted(set(current_gaps) - set(base_gaps)):
        lines.append(f"{corpus}: new documented known gap {case_id}")

    negative_now = set(report.get("negative_false_positives", []))
    negative_before = set(baseline.get("negative_false_positives", []))
    if negative_now - negative_before:
        lines.append(
            f"{corpus}: NEW negative false positives: "
            f"{sorted(negative_now - negative_before)}"
        )
    micro_current, micro_base = report["micro"], baseline.get("micro", {})
    if micro_base and micro_current["f1"] != micro_base.get("f1"):
        lines.append(
            f"{corpus}: micro F1 {micro_base.get('f1'):.3f} -> {micro_current['f1']:.3f}"
        )
    return lines


def baseline_regressions(lines: list[str]) -> bool:
    """True when a comparison produced actionable, exit-worthy regressions."""
    return any(
        "NEW REGRESSIONS" in line or "NEW negative false positives" in line
        for line in lines
    )


def run_corpora(
    corpus_paths: list[Path],
    extractor: Callable[[str], dict[str, Any]] | None = None,
    engine: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate each corpus independently; never combine their denominators."""
    if not corpus_paths:
        raise ValueError("at least one corpus path is required")
    return [run(path, extractor, engine or DEFAULT_ENGINE_LABEL) for path in corpus_paths]


def resolve_engine(spec: str) -> tuple[Callable[[str], dict[str, Any]], str]:
    """Resolve an adapter engine named 'module:attribute' for corpus bake-offs.

    The default engine must stay importable in CI (default: no extra argument);
    a candidate engine only needs the same input/output shape as the current
    one, so the corpora can compare them without touching backend code.
    """
    module_name, _, attr_name = spec.partition(":")
    if not module_name or not attr_name:
        raise SystemExit(f"error: --engine must look like module:attribute, got {spec!r}")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise SystemExit(f"error: cannot import engine module {module_name!r}: {exc}")
    engine = getattr(module, attr_name, None)
    if not callable(engine):
        raise SystemExit(f"error: engine {spec!r} is not callable")
    return engine, spec


def preprocessing_diagnosis(
    cases: list[dict[str, Any]], extractor: Callable[[str], dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Evidence-only diagnostic: which known-gap cases exact-match after normalization.

    Runs the default (or provided) engine on raw versus conservatively
    normalized text for every known-gap case. Scores and exit codes are never
    affected. See ``ai/normalize.py`` for the deliberate scope limits.
    """
    from ai.normalize import normalize_text  # local: keep the report importable

    extractor = extractor or DEFAULT_ENGINE
    repaired: dict[str, list[str]] = {}
    unrepairable: list[str] = []
    raised: list[str] = []
    for case in cases:
        if not case.get("known_gap"):
            continue
        try:
            raw = {
                name: value
                for name, value in (
                    (k, _plain_value(v)) for k, v in extractor(case["text"]).items()
                )
                if value is not None
            }
            payload, changes = normalize_text(case["text"])
            normalized = {
                name: value
                for name, value in (
                    (k, _plain_value(v)) for k, v in extractor(payload).items()
                )
                if value is not None
            }
        except Exception:  # noqa: BLE001 - diagnosis never masks the error shape
            raised.append(case["case_id"])
            continue
        if raw == case["expected"]:
            unrepairable.append(case["case_id"])  # flagged gap already passes? defensive
        elif normalized == case["expected"]:
            repaired[case["case_id"]] = [c["rule"] for c in changes]
        else:
            unrepairable.append(case["case_id"])
    return {
        "repaired": repaired,
        "not_fixed_by_these_rules": unrepairable,
        "extraction_raised": raised,
    }


def print_preprocessing_diagnosis(diagnosis: dict[str, Any]) -> None:
    repaired = diagnosis["repaired"]
    total = len(repaired) + len(diagnosis["not_fixed_by_these_rules"]) + len(diagnosis["extraction_raised"])
    print("preprocessing diagnosis (evaluation-only evidence, not scored):")
    print(
        f"  conservative normalization alone exact-matches "
        f"{len(repaired)}/{total} known-gap cases"
        + (f": {', '.join(sorted(repaired))}" if repaired else "")
    )
    rules = sorted({rule for ids in repaired.values() for rule in ids})
    if rules:
        print(f"  rules that fired: {', '.join(rules)}")
    if diagnosis["extraction_raised"]:
        print(f"  extraction raised on: {', '.join(diagnosis['extraction_raised'])}")
    print(
        "  adopting any preprocessing in production is a backend-owned change "
        "(see ai/BACKEND_HANDOFF.md); the flag changes no scores or exit codes"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score synthetic OCR field extraction")
    parser.add_argument(
        "--corpus",
        type=Path,
        action="append",
        help="corpus to evaluate; repeat to report independent slices",
    )
    parser.add_argument("--json", type=Path, help="also write the full report as JSON here")
    parser.add_argument(
        "--compare",
        type=Path,
        help="compare this run against a stored baseline JSON report; the baseline "
        "is only read, never written or updated",
    )
    parser.add_argument(
        "--engine",
        help="adapter engine for this run as module:attribute; used for labelled "
        "corpus bake-offs. Defaults to the current backend pipeline",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="after the report(s), print the evidence-only preprocessing "
        "diagnosis for known-gap cases (no effect on scores or exit codes)",
    )
    parser.add_argument("--quiet", action="store_true", help="print one summary line only")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 on any scored mismatch: a negative case extracting a field, a "
        "scored case raising, or a scored case not matching exactly; documented "
        "known gaps are exempt",
    )
    args = parser.parse_args(argv)

    extractor, engine_label = resolve_engine(args.engine) if args.engine else (None, DEFAULT_ENGINE_LABEL)
    reports = run_corpora(args.corpus or [CORPUS_PATH], extractor=extractor, engine=engine_label)
    report = reports[0] if len(reports) == 1 else None
    if args.json:
        payload: dict[str, Any]
        if report is not None:
            payload = report
        else:
            payload = {"banner": BANNER, "corpora": reports}
        args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.quiet:
        for current in reports:
            print(
                f"synthetic corpus {current['corpus']}: {current['cases']} cases, "
                f"exact-match {current['exact_match_count']}/{current['cases']}, "
                f"micro F1 {current['micro']['f1']:.3f}, "
                f"negative false positives {current['negative_false_positive_count']}, "
                f"known gaps {len(current['known_gaps'])}"
            )
    else:
        print(BANNER)
        print()
        for index, current in enumerate(reports):
            if index:
                print("\n" + "=" * 80 + "\n")
            _print_human(current, show_banner=False)

    if args.normalize:
        for path in args.corpus or [CORPUS_PATH]:
            print(f"corpus: {path}")
            print_preprocessing_diagnosis(preprocessing_diagnosis(load_corpus(path), extractor))

    if args.compare:
        try:
            baseline_payload = json.loads(args.compare.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SystemExit(f"error: baseline not found: {args.compare}")
        except json.JSONDecodeError as error:
            raise SystemExit(f"error: {args.compare}: {error}")
        try:
            baselines = _normalise_baseline(baseline_payload)
        except ValueError as error:
            raise SystemExit(f"error: {args.compare}: {error}")
        diff_lines: list[str] = []
        for current in reports:
            baseline = _match_baseline(current, baselines)
            diff_lines.extend(compare_to_baseline(current, baseline))
        for line in diff_lines:
            print(line)
        if baseline_regressions(diff_lines):
            return 1

    if args.check:
        failed = False
        for current in reports:
            if current["errors"]:
                print(
                    f"error: cases raised during extraction in {current['corpus']}",
                    file=sys.stderr,
                )
                failed = True
            if current["negative_false_positive_count"]:
                print(
                    f"error: negative cases produced spurious extractions in {current['corpus']}; "
                    "the extractor must leave unresolved values unresolved",
                    file=sys.stderr,
                )
                failed = True
            if current["exact_match_count"] != current["cases"]:
                print(
                    f"error: scored cases did not match exactly in {current['corpus']}; "
                    "unexpected extraction mismatches must be fixed or documented",
                    file=sys.stderr,
                )
                failed = True
        if failed:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

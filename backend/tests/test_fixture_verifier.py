"""Focused strictness tests for frontend fixture response comparisons."""

from frontend.tools.verify_fixtures import _compare


def _problems(actual: object, expected: object, path: str) -> list[str]:
    problems: list[str] = []
    _compare(actual, expected, path, problems)
    return problems


def test_different_valid_evaluation_dates_are_ignored_only_at_finding_fields() -> None:
    assert not _problems(
        "2026-10-31", "2026-10-30", "case.findings[0].evidence.evaluation_date"
    )
    assert not _problems(
        "Expired on 2020-01-01 before evaluation date 2026-10-31.",
        "Expired on 2020-01-01 before evaluation date 2026-10-30.",
        "case.findings[0].message",
    )


def test_expiry_date_changes_are_rejected() -> None:
    assert _problems(
        "2020-01-02", "2020-01-01", "case.findings[0].evidence.expiry_date"
    )


def test_finding_code_changes_are_rejected() -> None:
    assert _problems(
        "DOCUMENT_MISSING", "DOCUMENT_EXPIRED", "case.findings[0].code"
    )


def test_status_changes_are_rejected() -> None:
    assert _problems("attention_required", "preliminary_checks_passed", "case.status")


def test_unrelated_finding_message_changes_are_rejected() -> None:
    assert _problems(
        "The document expiry date 2020-01-01 is before the evaluation date 2026-10-31.",
        "Document expiry date 2020-01-01 is before the evaluation date 2026-10-30.",
        "case.findings[0].message",
    )
    assert _problems(
        "A changed message without an evaluation date.",
        "Original message without an evaluation date.",
        "case.findings[0].message",
    )


def test_malformed_evaluation_dates_are_rejected_even_when_equal() -> None:
    assert _problems(
        "2026-02-30", "2026-02-30", "case.findings[0].evidence.evaluation_date"
    )
    assert _problems(
        "Expired before evaluation date 2026-02-30.",
        "Expired before evaluation date 2026-02-30.",
        "case.findings[0].message",
    )

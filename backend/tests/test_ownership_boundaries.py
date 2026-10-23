"""Ownership-boundary guard.

The three-workstream split is only real if a change that crosses a boundary is
detectable before it lands. `tools/check_ownership.py` implements the rules in
WORKSTREAMS.md; these tests pin its behaviour and exercise the CLI the way a
contributor or CI would.

This module lives in `backend/tests/` because that is the only directory pytest
collects (`pyproject.toml` -> `testpaths`). It is integration-owned, not part of
workstream B: `backend/tests/test_ownership_boundaries.py` is listed in
`INTEGRATION_GUARD_FILES`, so a backend change touching it is itself reported as
a violation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.check_ownership import check, classify

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "check_ownership.py"


def test_classify_covers_every_ownership_class():
    assert classify("frontend/fixtures/validate-ok.json") == "frontend"
    assert classify("backend/app/main.py") == "backend"
    assert classify("ai/corpus/extraction_cases.jsonl") == "ai"
    assert classify("docs/development/API_CONTRACT.md") == "shared"
    assert classify(".github/workflows/backend-tests.yml") == "shared"
    assert classify("WORKSTREAMS.md") == "shared"
    assert classify("pyproject.toml") == "shared"
    assert classify("tools/check_ownership.py") == "shared"
    assert classify("backend/app/ocr_pipeline.py") == "ocr-backend"
    assert classify("backend/tests/test_ocr_pipeline.py") == "ocr-backend"
    assert classify("backend/tests/fixtures/institution_ocr_cases.jsonl") == "ocr-backend"
    assert classify("backend/tests/test_ci_configuration.py") == "integration-guard"
    assert classify("setup.py") == "unknown"


def test_workstream_may_change_its_own_directory():
    assert check(["backend/app/main.py", "backend/tests/test_api_contract.py"], "backend") == []
    assert check(["frontend/fixtures/validate-ok.json"], "frontend") == []
    assert check(["ai/corpus/extraction_cases.jsonl"], "ai") == []


def test_backend_owns_the_ocr_implementation_today():
    assert check(["backend/app/ocr_pipeline.py"], "backend") == []


def test_crossing_into_another_workstream_is_rejected():
    violations = check(["backend/app/main.py"], "frontend")
    assert len(violations) == 1
    assert "backend" in violations[0] and "frontend" in violations[0]


def test_ai_cannot_land_ocr_implementation_changes_alone():
    violations = check(["backend/app/ocr_pipeline.py"], "ai")
    assert len(violations) == 1
    assert "owned by 'backend'" in violations[0]


def test_shared_paths_need_an_explicit_declaration():
    violations = check(["docs/development/API_CONTRACT.md"], "backend")
    assert len(violations) == 1
    assert "--declare-shared" in violations[0]

    declared = check(
        ["docs/development/API_CONTRACT.md"],
        "backend",
        declared_shared=["docs/development/API_CONTRACT.md"],
    )
    assert declared == []


def test_root_configuration_is_shared_not_owned():
    for path in ("pyproject.toml", "README.md", ".github/workflows/backend-tests.yml"):
        assert check([path], "backend"), f"{path} must require a declaration"


def test_guard_tests_cannot_be_weakened_by_a_workstream():
    for workstream in ("frontend", "backend", "ai"):
        violations = check(["backend/tests/test_ci_configuration.py"], workstream)
        assert violations, f"{workstream} must not edit the CI guard test"
        assert "integration guard" in violations[0]


def test_integration_workstream_may_change_shared_paths():
    assert check(["docs/development/OWNER_ACTIONS.md"], "integration") == []
    assert check(["backend/tests/test_ownership_boundaries.py"], "integration") == []


def test_integration_workstream_needs_a_declaration_to_touch_a_workstream_folder():
    violations = check(["backend/app/main.py"], "integration")
    assert len(violations) == 1
    assert "--declare-shared" in violations[0]
    assert check(["backend/app/main.py"], "integration", ["backend/app/main.py"]) == []


def test_unrecognised_root_paths_are_treated_as_shared():
    violations = check(["setup.py"], "backend")
    assert len(violations) == 1
    assert "unrecognised" in violations[0]


def test_empty_change_set_is_clean():
    assert check([], "frontend") == []


def test_unknown_workstream_is_rejected():
    try:
        check(["backend/app/main.py"], "design")
    except ValueError as error:
        assert "unknown workstream" in str(error)
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("an unknown workstream must raise ValueError")


def _run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_passes_a_change_list_on_stdin():
    result = _run(
        "--workstream",
        "frontend",
        "--paths-from",
        "-",
        stdin="frontend/fixtures/validate-ok.json\n",
    )
    assert result.returncode == 0, result.stderr
    assert "ownership OK" in result.stdout


def test_cli_fails_a_cross_boundary_change_and_names_the_path():
    result = _run(
        "--workstream", "frontend", "--paths-from", "-", stdin="backend/app/main.py\n"
    )
    assert result.returncode == 1
    assert "backend/app/main.py" in result.stderr


def test_cli_reads_the_git_diff_when_given_a_base():
    # HEAD against itself is an empty diff: the check must succeed, not crash.
    result = _run("--workstream", "integration", "--base", "HEAD")
    assert result.returncode == 0, result.stderr
    assert "0 changed path(s)" in result.stdout


def test_cli_rejects_an_unusable_base_ref():
    result = _run("--workstream", "backend", "--base", "refs/heads/does-not-exist")
    assert result.returncode == 2
    assert "error:" in result.stderr


def test_cli_accepts_several_declarations_after_one_flag():
    result = _run(
        "--workstream",
        "integration",
        "--paths-from",
        "-",
        "--declare-shared",
        "frontend/README.md",
        "ai/README.md",
        stdin="frontend/README.md\nai/README.md\n",
    )
    assert result.returncode == 0, result.stderr
    assert "ownership OK" in result.stdout


def test_cli_rejects_an_unknown_workstream():
    result = _run("--workstream", "design", "--paths-from", "-", stdin="")
    assert result.returncode != 0

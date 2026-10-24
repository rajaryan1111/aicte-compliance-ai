#!/usr/bin/env python3
"""Check that a change stays inside the workstream that owns it.

Ownership rules live in ``WORKSTREAMS.md``. This script turns them into a
deterministic check so "I only touched my own folder" is verifiable instead of
asserted. It reads a list of changed paths and reports the ones the named
workstream may not change without an explicit declaration.

Usage
-----
    # locally, before opening a PR
    python tools/check_ownership.py --workstream backend \
        --base origin/research/grounded-foundation

    # against an explicit list (also useful in CI or tests)
    git diff --name-only --no-renames origin/research/grounded-foundation...HEAD \
        | python tools/check_ownership.py --workstream frontend --paths-from -

    # shared-file change, deliberately declared (needs reviewer agreement)
    python tools/check_ownership.py --workstream backend --base origin/main \
        --declare-shared docs/development/API_CONTRACT.md

Exit codes
----------
    0  every changed path is owned by the workstream, is a declared shared
       change, or the change set is empty
    1  at least one violation (printed)
    2  usage error (unknown workstream, unusable base ref)

Limitations, stated so nobody over-trusts it
--------------------------------------------
* It checks *paths*, not intent. A frontend contributor putting backend logic
  in ``frontend/`` still passes; review catches that, not this script.
* Declarations are not verified against a review record. ``--declare-shared``
  records an assertion; it does not prove the other owners agreed.
* It says nothing about whether a change is correct, tested or safe.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable, Sequence

WORKSTREAMS: dict[str, str] = {
    "frontend": "frontend/",
    "backend": "backend/",
    "ai": "ai/",
}

# Integration surfaces: no single workstream owns these.
SHARED_PREFIXES: tuple[str, ...] = ("docs/", ".github/", "tools/")
SHARED_ROOT_FILES: frozenset[str] = frozenset(
    {
        "README.md",
        "WORKSTREAMS.md",
        "pyproject.toml",
        ".gitignore",
        ".env.example",
        ".python-version",
        "docker-compose.integration.yml",
    }
)

# Guard tests enforced by CI. They live under backend/tests because that is the
# only directory pytest collects, but they are integration-owned: a backend
# change must not be able to weaken the checks that police backend changes.
INTEGRATION_GUARD_FILES: frozenset[str] = frozenset(
    {
        "backend/tests/test_ci_configuration.py",
        "backend/tests/test_docs_links.py",
        "backend/tests/test_ownership_boundaries.py",
    }
)

# The OCR implementation currently lives in backend/ and is owned by the backend
# workstream until a reviewed migration says otherwise (WORKSTREAMS.md).
OCR_PREFIXES: tuple[str, ...] = (
    "backend/app/ocr_",
    "backend/tests/test_ocr_",
)
OCR_FIXTURES: frozenset[str] = frozenset({"backend/tests/fixtures/institution_ocr_cases.jsonl"})


def classify(path: str) -> str:
    """Return the ownership class of a repository-relative path."""
    if path in INTEGRATION_GUARD_FILES:
        return "integration-guard"
    if path in OCR_FIXTURES or path.startswith(OCR_PREFIXES):
        return "ocr-backend"
    for workstream, prefix in WORKSTREAMS.items():
        if path.startswith(prefix):
            return workstream
    if path in SHARED_ROOT_FILES or path.startswith(SHARED_PREFIXES):
        return "shared"
    return "unknown"


def check(
    paths: Iterable[str],
    workstream: str,
    declared_shared: Sequence[str] = (),
) -> list[str]:
    """Return a list of human-readable violations (empty means clean)."""
    if workstream not in WORKSTREAMS and workstream != "integration":
        raise ValueError(
            f"unknown workstream {workstream!r}; expected one of "
            f"{sorted(WORKSTREAMS) + ['integration']}"
        )

    declared = {path.strip() for path in declared_shared if path.strip()}
    violations: list[str] = []

    for path in sorted({p.strip() for p in paths if p.strip()}):
        owner = classify(path)

        if workstream == "integration":
            # The integration PR owns shared surfaces outright. A workstream's
            # own folder is edited by that workstream, or here only when the
            # cross-folder change is declared and therefore reviewable.
            if (owner in WORKSTREAMS or owner == "ocr-backend") and path not in declared:
                violations.append(
                    f"{path}: owned by '{owner}'; an integration change to another "
                    "workstream's folder needs --declare-shared and that owner's review"
                )
            continue

        if owner in WORKSTREAMS and owner != workstream:
            violations.append(
                f"{path}: owned by workstream '{owner}', changed by '{workstream}'"
            )
            continue
        if owner == "integration-guard":
            violations.append(
                f"{path}: integration guard test, not owned by any workstream; "
                "propose the change through the integration PR"
            )
            continue
        if owner == "ocr-backend" and workstream == "ai":
            violations.append(
                f"{path}: OCR implementation is owned by 'backend' until a reviewed "
                "migration; 'ai' may propose but must not land it alone"
            )
            continue

        if owner in {"shared", "unknown"} and path not in declared:
            kind = "shared" if owner == "shared" else "unrecognised (treat as shared)"
            violations.append(
                f"{path}: {kind} path changed without --declare-shared; "
                "open a separate proposal/integration PR"
            )

    return violations


def changed_paths(base: str, head: str = "HEAD") -> list[str]:
    """Paths changed between the merge base of ``base`` and ``head``."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git diff failed for {base}...{head}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _read_paths(source: str) -> list[str]:
    if source == "-":
        return [line.strip() for line in sys.stdin if line.strip()]
    with open(source, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--workstream",
        required=True,
        choices=sorted(WORKSTREAMS) + ["integration"],
        help="which workstream is making the change",
    )
    parser.add_argument("--base", help="git ref to diff against, e.g. origin/main")
    parser.add_argument("--head", default="HEAD", help="git ref being checked (default HEAD)")
    parser.add_argument(
        "--paths-from",
        metavar="FILE",
        help="read changed paths from FILE ('-' for stdin) instead of git diff",
    )
    parser.add_argument(
        "--declare-shared",
        action="append",
        nargs="+",
        default=[],
        metavar="PATH",
        help=(
            "shared path(s) this change intentionally touches; repeatable, and accepts "
            "several paths after one flag: --declare-shared docs/a.md frontend/README.md"
        ),
    )
    args = parser.parse_args(argv)

    try:
        if args.paths_from:
            paths = _read_paths(args.paths_from)
        elif args.base:
            paths = changed_paths(args.base, args.head)
        else:
            parser.error("pass either --base or --paths-from")
        declared = [path for group in args.declare_shared for path in group]
        violations = check(paths, args.workstream, declared)
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not violations:
        print(f"ownership OK: {len(paths)} changed path(s) fit workstream '{args.workstream}'")
        return 0

    print(f"ownership violations for workstream '{args.workstream}':", file=sys.stderr)
    for violation in violations:
        print(f"  - {violation}", file=sys.stderr)
    print(
        "\nEither move the change into the owning folder, or open a separate "
        "proposal/integration PR (see WORKSTREAMS.md).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

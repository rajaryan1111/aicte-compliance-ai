"""Keep relative links in the repository's markdown honest.

Three workstreams now share a documentation set, and a link that points at a
file that was renamed, never written, or whose heading changed is the cheapest
way to lose a reader. This checks relative links and same-repository anchors.
External URLs are not fetched (CI has no network guarantee) and links that
leave the repository are skipped.

The anchor algorithm mirrors GitHub's slug rules for the subset used here:
lower-case, drop everything except letters, digits, spaces and hyphens, then
replace spaces with hyphens. Duplicate headings (`-1` suffixes) are not handled
because the documentation does not use them.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)?(#[^)\s]+)?\)")
FENCE = re.compile(r"```.*?```", re.DOTALL)
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
SKIP_SCHEMES = ("http://", "https://", "mailto:")

# Directories that are not part of the documentation surface.
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}


def _markdown_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def _slug(heading: str) -> str:
    lowered = heading.strip().lower()
    stripped = re.sub(r"[^a-z0-9 \-]", "", lowered)
    return stripped.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    return {_slug(heading) for heading in HEADING.findall(text)}


def test_relative_markdown_links_resolve():
    assert _markdown_files(), "no markdown files found"

    broken = []
    for path in _markdown_files():
        text = FENCE.sub("", path.read_text(encoding="utf-8"))
        for target, fragment in LINK.findall(text):
            if target and target.startswith(SKIP_SCHEMES):
                continue
            if not target and not fragment:
                continue
            destination = (path.parent / target).resolve() if target else path
            if not destination.exists():
                broken.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
                continue
            if fragment and destination.suffix == ".md":
                anchor = fragment.lstrip("#")
                if anchor not in _anchors(destination):
                    broken.append(
                        f"{path.relative_to(REPO_ROOT)} -> {target}{fragment} (no such heading)"
                    )

    assert not broken, "broken relative links:\n" + "\n".join(broken)

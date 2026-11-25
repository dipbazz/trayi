"""CLAUDE.md pulls in AGENTS.md, each agent's personal override file stays out of git, and the
workflow skill's pointers into docs/ lead somewhere."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_SKILL = ROOT / ".claude" / "skills" / "workflow" / "SKILL.md"
# A pointer names a docs file by its repo path, and a section by its exact heading:
# `docs/contributing/reviews.md`, "When a review is done"
# or by an anchor: `docs/contributing/reviews.md#when-a-review-is-done`
POINTER = re.compile(r'`(docs/[^`\s#]+\.md)(?:#([^`\s]+))?`(?:,\s+"([^"]+)")?')
BACKTICKED_MD = re.compile(r"`([^`\s]+\.md)(?:#[^`]*)?`")


def _headings(path, deepest=6):
    """The text of every Markdown heading in a file down to h<deepest>, outside fenced code."""
    headings, in_fence = set(), False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and re.match(rf"#{{1,{deepest}}} ", line):
            headings.add(line.lstrip("#").strip())
    return headings


def _anchors(path):
    """The anchors MyST gives a file's headings: myst_heading_anchors = 3 in docs/conf.py, and
    the slug of myst_parser's default_slugify (GitHub's)."""
    clean = re.compile(r"[^\w一-鿿\- ]")
    return {clean.sub("", h.lower().replace(" ", "-")) for h in _headings(path, deepest=3)}


def test_claude_md_reads_agents_md():
    lines = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert "@AGENTS.md" in lines


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.local.md",  # Claude Code: personal instructions
        ".claude/settings.local.json",  # Claude Code: personal permissions
        "AGENTS.override.md",  # Codex: personal instructions
    ],
)
def test_override_file_is_ignored(path):
    # -v names the file whose rule matched, so a personal ignore (the global excludes file or
    # .git/info/exclude) can't hide a missing line here.
    result = subprocess.run(
        ["git", "check-ignore", "--verbose", "--no-index", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    source = result.stdout.split(":", 1)[0]
    assert result.returncode == 0 and source == ".gitignore", f"{path} isn't in .gitignore"


def broken_pointers(text):
    """The pointers in text whose file, heading or #anchor doesn't exist."""
    broken = []
    for doc, anchor, heading in POINTER.findall(text):
        heading = " ".join(heading.split())  # a quoted heading can wrap onto the next line
        if not (ROOT / doc).is_file():
            broken.append(doc)
        elif heading and heading not in _headings(ROOT / doc):
            broken.append(f'{doc}, "{heading}"')
        elif anchor and anchor not in _anchors(ROOT / doc):
            broken.append(f"{doc}#{anchor}")
    return broken


def test_workflow_skill_points_at_docs_that_exist():
    # The skill is mostly pointers into docs/, and the docs build checks only links inside
    # docs/, so a renamed heading would leave the skill pointing at nothing.
    text = WORKFLOW_SKILL.read_text(encoding="utf-8")
    assert any(heading for *_, heading in POINTER.findall(text)), "no quoted section: style?"
    broken = broken_pointers(text)
    assert not broken, f"the workflow skill points at what doesn't exist: {broken}"


@pytest.mark.parametrize(
    "pointer",
    [
        "`docs/contributing/reviews.md#no-such-section`",
        "`docs/contributing/no-such-page.md#tools`",
    ],
)
def test_a_pointer_with_an_anchor_is_checked_too(pointer):
    assert broken_pointers(pointer)


def test_a_pointer_to_a_headings_anchor_is_not_broken():
    assert broken_pointers("`docs/contributing/reviews.md#when-a-review-is-done`") == []


def test_workflow_skill_names_docs_by_path():
    # One style keeps the pointer test above able to read every pointer: `reviews.md` alone
    # would go unchecked.
    docs_names = {path.name for path in (ROOT / "docs").rglob("*.md")}
    named = BACKTICKED_MD.findall(WORKFLOW_SKILL.read_text(encoding="utf-8"))
    bare = sorted({name for name in named if not name.startswith("docs/") and name in docs_names})
    assert not bare, f"name these by their path from the repo root, docs/...: {bare}"

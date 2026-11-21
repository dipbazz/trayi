"""Refuse a commit that leaves CLAUDE.md and AGENTS.md together over their word limit.

A pre-commit hook (.pre-commit-config.yaml). Claude Code reads both files at every session start
(CLAUDE.md pulls in AGENTS.md with an @AGENTS.md line), so detail belongs in docs/ or a skill
(docs/decisions.md, "Checks before each commit with pre-commit"). The script always reads both
files from the current directory, whichever one a commit touches; a missing file counts 0.
"""

import sys
from pathlib import Path

LIMIT = 600


def read_both(root):
    """The text of CLAUDE.md and AGENTS.md under root, "" for a missing file."""
    return tuple(
        path.read_text(encoding="utf-8") if path.exists() else ""
        for path in (root / "CLAUDE.md", root / "AGENTS.md")
    )


def problem(claude_text, agents_text=""):
    """The message to show when the two files together are over the limit, or None."""
    claude, agents = len(claude_text.split()), len(agents_text.split())
    total = claude + agents
    if total <= LIMIT:
        return None
    return (
        f"CLAUDE.md ({claude}) and AGENTS.md ({agents}) are {total} words together, "
        f"over their {LIMIT}-word limit.\n"
        "Move detail to docs/ or a skill (.claude/skills/), leaving a short pointer."
    )


def main():
    message = problem(*read_both(Path.cwd()))
    if message:
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

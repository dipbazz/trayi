"""CLAUDE.md pulls in AGENTS.md, and each agent's personal override file stays out of git."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


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

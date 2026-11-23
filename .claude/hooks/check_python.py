"""Format a Python file as soon as Claude Code changes it, and report what ruff finds.

A PostToolUse hook on Edit and Write of a `.py` file (.claude/settings.json). It runs ruff with
pre-commit's command and flags: `ruff format`, which fixes the layout in place, then `ruff check`,
whose findings go back to Claude (exit 2). It never runs `ruff check --fix`, which would delete an
import added one edit before the code that uses it. pre-commit and CI stay check-only.

Only a file inside the clone that git doesn't ignore is checked, the files pre-commit sees: ruff
lints any file it's given by path, `local/` and scratch files too. When ruff can't run (not
installed before `uv sync`, or uv missing), the person is told, not Claude.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# .pre-commit-config.yaml's ruff entries, formatting rather than `--check`; a test keeps them equal.
FORMAT = "uv run --no-sync ruff format --force-exclude".split()
CHECK = "uv run --no-sync ruff check --force-exclude".split()


def checked_path(file_path):
    """The file's path inside the clone, or None when pre-commit wouldn't see it."""
    path = Path(file_path)
    if path.suffix != ".py":
        return None
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return None
    # check-ignore exits 0 for an ignored file, 1 for one it isn't, 128 when it can't tell.
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative.as_posix()],
        cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True,
    )  # fmt: skip
    return relative if ignored.returncode == 1 else None


def ruff(command, path):
    """ruff's exit code and output; exit 2, as ruff's own error, when it couldn't be started."""
    try:
        result = subprocess.run(
            [*command, str(path)], cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )  # fmt: skip
    except OSError as error:
        return 2, str(error)
    return result.returncode, (result.stdout + result.stderr).strip()[-3000:]


def main():
    try:
        file_path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
    except ValueError:
        return 0
    path = checked_path(file_path)
    if path is None:
        return 0
    # A file ruff can't parse fails to format; `ruff check` then reports why, as a finding.
    format_code, format_output = ruff(FORMAT, path)
    check_code, check_output = ruff(CHECK, path)
    if check_code == 1:  # ruff's code for findings
        print(f"ruff check found problems in {path}; fix them:\n{check_output}", file=sys.stderr)
        return 2
    if check_code == 0 and format_code == 0:
        return 0
    # uv or ruff couldn't run: tell the person, without waking Claude to "fix" the file.
    output = check_output if check_code else format_output
    print(f"Couldn't run ruff on {path}:\n{output}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

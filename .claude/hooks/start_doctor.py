#!/usr/bin/env -S uv run --script
# /// script
# # Its own environment in uv's cache, like doctor's: it installs no package.
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Run doctor's check when a Claude Code session starts, and pass its lines to the agent.

A SessionStart hook on `startup` only (.claude/settings.json), run with `uv run --script`. It
runs `scripts/doctor.py --check`, which reports and changes nothing, and prints a header and
doctor's lines, so the agent starts knowing what to fix (AGENTS.md: run doctor before other
work). doctor itself doesn't know about Claude Code.

doctor's output goes to a temporary file, not a pipe, as doctor does for its own children: on
Windows a git helper that outlives a stopped command holds a pipe open and hangs the read.
doctor is stopped after DEADLINE seconds, keeping the lines it printed, well inside the hook's
own timeout: Claude Code drops everything a hook printed once that passes. It always exits 0,
since Claude Code passes a SessionStart hook's output to the agent only then.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR = [sys.executable, str(ROOT / "scripts" / "doctor.py"), "--check"]
DEADLINE = 40  # seconds; settings.json gives the hook 90, for uv's first download of Python
HEADER = (
    "Claude Code's start-up hook (.claude/hooks/start_doctor.py) already ran"
    " `uv run --script scripts/doctor.py --check` in this clone; its lines are below. Run doctor"
    " again only without `--check`, to bring .venv in line with uv.lock, or after fixing what it"
    " reports."
)


def run_doctor():
    """doctor's output, and a note when it had to be stopped."""
    with tempfile.TemporaryFile() as out:
        note = ""
        try:
            subprocess.run(
                DOCTOR, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                timeout=DEADLINE,
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            note = f"doctor didn't finish in {DEADLINE} s: the lines above are the checks it ran."
        out.seek(0)
        return out.read().decode("utf-8", "replace").strip(), note


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # doctor's ✓, ⚠️ and ❌ on any console
    print(HEADER)
    try:
        output, note = run_doctor()
    except Exception as error:  # the session must start whatever went wrong
        print(f"The start-up hook couldn't run doctor: {error}")
        return 0
    print(output)
    if note:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())

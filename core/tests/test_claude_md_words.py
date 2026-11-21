"""The pre-commit word limit on CLAUDE.md and AGENTS.md together.

The check is scripts/check_claude_md_words.py.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_claude_md_words.py"
spec = importlib.util.spec_from_file_location("check_claude_md_words", SCRIPT)
check_claude_md_words = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_claude_md_words)


def words(n):
    return " ".join(["word"] * n)


def test_accepts_the_limit_across_both_files():
    assert check_claude_md_words.problem(words(300), words(300)) is None


def test_refuses_one_word_over_across_both_files():
    message = check_claude_md_words.problem(words(300), words(301))
    assert "601" in message
    assert "600" in message
    assert "CLAUDE.md" in message
    assert "AGENTS.md" in message


def test_the_repository_files_are_within_the_limit():
    root = SCRIPT.parents[1]
    assert check_claude_md_words.problem(*check_claude_md_words.read_both(root)) is None


def run_check(cwd, claude, agents=None):
    (cwd / "CLAUDE.md").write_text(words(claude), encoding="utf-8")
    if agents is not None:
        (cwd / "AGENTS.md").write_text(words(agents), encoding="utf-8")
    # The hook passes no filenames (pass_filenames: false): the script reads both itself.
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=cwd, capture_output=True, text=True)


def test_the_script_refuses_601_words_across_both_files(tmp_path):
    result = run_check(tmp_path, 150, 451)
    assert result.returncode == 1
    assert "601" in result.stderr


def test_the_script_accepts_600_words_across_both_files(tmp_path):
    result = run_check(tmp_path, 150, 450)
    assert result.returncode == 0
    assert result.stderr == ""


def test_a_missing_agents_md_counts_0(tmp_path):
    assert run_check(tmp_path, 600).returncode == 0
    assert run_check(tmp_path, 601).returncode == 1

"""The Claude Code hooks in .claude/hooks/ (docs/decisions.md, "Claude Code hooks ...")."""

import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pytest_scope = load("pytest_scope")
check_stylesheet = load("check_stylesheet")
review_workflow = load("review_workflow")


def run_hook(hook, tool_input, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": tool_input})))
    return hook.main()


@pytest.fixture
def no_failures_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(pytest_scope, "LAST_FAILED", tmp_path / "lastfailed", raising=False)


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest",
        "uv run pytest -q",
        'uv run pytest -m "not browser"',
        "python -m pytest",
        "py -m pytest",
        "uv run pytest -x; ls",
        "uv run pytest .",
        "uv run pytest --cov charity",
        "uv run pytest --junitxml out/report.xml",
        "uv run pytest > C:/tmp/out.txt",
        "echo start\nuv run pytest",
        "uv run pytest \\\n  -q",
        "uv run --directory . pytest",
        "uv run --only-group test pytest",
        "timeout 900 uv run pytest",
        "env X=1 pytest",
        "uv run pytest --sw",
        "uv run pytest --lf",
    ],
)
def test_a_whole_suite_run_is_blocked(command, no_failures_recorded, monkeypatch):
    assert run_hook(pytest_scope, {"command": command}, monkeypatch) == 2


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest news",
        "uv run pytest core/tests/test_mail.py::test_send",
        "uv run pytest -k gift",
        'uv run pytest -m "not browser" core/tests',
        "uv run pytest --cov=core core/tests",
        "cd core && uv run pytest tests",
        "uv run pytest --version",
        "uv run pytest --co -q",
        "uv run pytest --fixtures",
        "git grep pytest",
        "echo 'uv run pytest'",
        "uv run ruff check .",
    ],
)
def test_a_narrowed_or_harmless_command_is_allowed(command, no_failures_recorded, monkeypatch):
    assert run_hook(pytest_scope, {"command": command}, monkeypatch) == 0


def test_last_failed_is_allowed_when_tests_failed_last_time(tmp_path, monkeypatch):
    last_failed = tmp_path / "lastfailed"
    last_failed.write_text(json.dumps({"core/tests/test_mail.py::test_send": True}))
    monkeypatch.setattr(pytest_scope, "LAST_FAILED", last_failed)

    assert run_hook(pytest_scope, {"command": "uv run pytest --lf"}, monkeypatch) == 0


def fake_test_run(monkeypatch, **result):
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, **{"stdout": "", "stderr": "", **result})

    monkeypatch.setattr(check_stylesheet.subprocess, "run", run)
    return calls


@pytest.mark.parametrize(
    "path",
    [
        check_stylesheet.ROOT / "README.md",
        # test_stylesheet.py checks only the stylesheets directly in the folder.
        check_stylesheet.CSS / "pages" / "gift.css",
    ],
)
def test_the_stylesheet_test_runs_only_for_a_stylesheet_it_checks(path, monkeypatch):
    calls = fake_test_run(monkeypatch, returncode=0)

    assert run_hook(check_stylesheet, {"file_path": str(path)}, monkeypatch) == 0
    assert calls == []


def test_a_failing_stylesheet_is_reported_to_claude(monkeypatch, capsys):
    fake_test_run(monkeypatch, returncode=1, stdout="FAILED max-width")

    exit_code = run_hook(
        check_stylesheet, {"file_path": str(check_stylesheet.CSS / "charity.css")}, monkeypatch
    )

    assert exit_code == 2
    assert "FAILED max-width" in capsys.readouterr().err


def test_a_test_that_cannot_run_is_not_reported_as_a_failing_stylesheet(monkeypatch, capsys):
    fake_test_run(monkeypatch, returncode=2, stderr="error: Failed to spawn: `pytest`")

    exit_code = run_hook(
        check_stylesheet, {"file_path": str(check_stylesheet.CSS / "charity.css")}, monkeypatch
    )

    err = capsys.readouterr().err
    assert exit_code == 1  # shown to the person, without waking Claude
    assert "Failed to spawn" in err
    assert "fails after this change" not in err


@pytest.fixture
def markers(tmp_path, monkeypatch):
    """Each test starts with no once-a-session markers."""
    monkeypatch.setattr(review_workflow, "MARKERS", tmp_path)
    return tmp_path


def review_hook(monkeypatch, capsys, prompt=None, skill=None, session_id="test-session"):
    if skill is not None:
        hook = {"hook_event_name": "PreToolUse", "tool_input": {"skill": skill}}
    else:
        hook = {"hook_event_name": "UserPromptSubmit", "prompt": prompt}
    hook["session_id"] = session_id
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(hook)))
    assert review_workflow.main() == 0  # a reminder never blocks the prompt or the skill
    return capsys.readouterr().out


@pytest.mark.parametrize(
    "prompt",
    [
        "/code-review high 323",
        "/qa-only",
        "/plan-design-review",
        "run code review on 323",
        "can you code review 323?",
        "do the design review for #325",
        "start the eng review",
        "let's finish the security review",
        "time for the product review of #325",
        "QA 323",
        "run qa on #323",
        "#325 needs: design review, start it",
        "#327 needs: qa",
    ],
)
def test_a_request_to_run_a_review_reminds(prompt, markers, monkeypatch, capsys):
    assert "label review" in review_hook(monkeypatch, capsys, prompt=prompt)


@pytest.mark.parametrize("command", sorted(review_workflow.REVIEW_SKILLS))
def test_each_review_command_reminds(command, markers, monkeypatch, capsys):
    assert "label review" in review_hook(monkeypatch, capsys, prompt=f"/{command} 323")


# Regression: "...so this long message body part may not be missed by the design review" (8 Nov)
# asked for a comment, not a review, and was told "This is a label review".
@pytest.mark.parametrize(
    "prompt",
    [
        "post a small comment so this long message may not be missed by the design review",
        "the product review decided to hold scope",
        "I am reviewing the PR 323 and thought of a new feature",
        "I tried QA with a slow connection and sent 3 forms",
        "the qa report found 2,000 characters",
    ],
)
def test_a_mention_of_a_review_doesnt_remind(prompt, markers, monkeypatch, capsys):
    assert review_hook(monkeypatch, capsys, prompt=prompt) == ""


@pytest.mark.parametrize("skill", ["code-review", "qa-only", "gstack:plan-eng-review"])
def test_starting_a_review_skill_reminds_whatever_the_prompt_said(
    skill, markers, monkeypatch, capsys
):
    """The safety net when a prompt's words aren't caught: Claude starting the skill itself."""
    output = json.loads(review_hook(monkeypatch, capsys, skill=skill))["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert "label review" in output["additionalContext"]


def test_another_skill_doesnt_remind(markers, monkeypatch, capsys):
    assert review_hook(monkeypatch, capsys, skill="workflow") == ""


def test_the_reminder_shows_once_a_session(markers, monkeypatch, capsys):
    review_hook(monkeypatch, capsys, prompt="/code-review high 323")
    assert review_hook(monkeypatch, capsys, skill="code-review") == ""
    assert "label review" in review_hook(
        monkeypatch, capsys, prompt="/code-review high 323", session_id="another-session"
    )


def test_the_reminder_shows_when_its_marker_cant_be_written(tmp_path, monkeypatch, capsys):
    # Better twice in a session than not at all.
    monkeypatch.setattr(review_workflow, "MARKERS", tmp_path / "missing")
    assert "label review" in review_hook(monkeypatch, capsys, prompt="/code-review high 323")


def test_input_that_isnt_json_is_ignored(markers, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert review_workflow.main() == 0
    assert capsys.readouterr().out == ""


def run_with_commands():
    """The commands in the "Run with" column of reviews.md's table of `needs:` labels."""
    commands = set()
    for line in (ROOT / "docs" / "contributing" / "reviews.md").read_text("utf-8").splitlines():
        if line.startswith("| `needs:"):
            commands |= set(re.findall(r"`/([a-z][a-z-]*)", line.rsplit("|", 2)[-2]))
    return commands


def test_the_review_commands_match_the_reviews_page():
    # /office-hours shapes a raw idea before any label asks for a review. /security-review is
    # Claude Code's own command, which people type for a security review.
    expected = (run_with_commands() - {"office-hours"}) | {"security-review"}
    assert review_workflow.REVIEW_SKILLS == expected

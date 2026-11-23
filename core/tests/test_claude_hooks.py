"""The Claude Code hooks in .claude/hooks/ (docs/decisions.md, "Claude Code hooks ...")."""

import importlib.util
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
import tomllib
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
start_doctor = load("start_doctor")
check_python = load("check_python")


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


@pytest.fixture
def fake_doctor(tmp_path, monkeypatch):
    """Point start_doctor.py at a stand-in doctor, a script whose body the test writes."""

    def make(body, deadline=start_doctor.DEADLINE):
        script = tmp_path / "doctor.py"
        # Like doctor, print UTF-8 whatever the console's code page.
        script.write_text('import sys\nsys.stdout.reconfigure(encoding="utf-8")\n' + body, "utf-8")
        monkeypatch.setattr(start_doctor, "DOCTOR", [sys.executable, str(script), "--check"])
        monkeypatch.setattr(start_doctor, "DEADLINE", deadline)

    return make


def start_up(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"source": "startup"})))
    assert start_doctor.main() == 0  # Claude Code passes the output on only after exit 0
    return capsys.readouterr().out


@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_doctors_lines_reach_the_agent_whatever_it_exits_with(
    exit_code, fake_doctor, monkeypatch, capsys
):
    fake_doctor(f"print('✓ uv 0.9.5')\nprint('❌ no git user.email')\nsys.exit({exit_code})")

    out = start_up(monkeypatch, capsys)

    assert "✓ uv 0.9.5" in out
    assert "❌ no git user.email" in out


def test_the_header_says_doctor_already_ran(fake_doctor, monkeypatch, capsys):
    fake_doctor('print("✓ uv 0.9.5")')

    header = start_up(monkeypatch, capsys).split("✓ uv 0.9.5")[0]

    assert "already ran `uv run --script scripts/doctor.py --check`" in header
    assert "without `--check`" in header


def test_a_crash_in_doctor_reaches_the_agent(fake_doctor, monkeypatch, capsys):
    fake_doctor('print("✓ uv 0.9.5", flush=True)\nraise RuntimeError("doctor broke")')

    out = start_up(monkeypatch, capsys)

    assert "✓ uv 0.9.5" in out
    assert "RuntimeError: doctor broke" in out


def test_a_doctor_that_cant_start_still_exits_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(start_doctor, "DOCTOR", [str(tmp_path / "missing"), "--check"])

    assert "couldn't run doctor" in start_up(monkeypatch, capsys)


def test_a_hung_doctor_is_stopped_and_its_lines_so_far_kept(fake_doctor, monkeypatch, capsys):
    fake_doctor('import time\nprint("✓ uv 0.9.5", flush=True)\ntime.sleep(60)', deadline=1)

    out = start_up(monkeypatch, capsys)

    assert "✓ uv 0.9.5" in out
    assert "doctor didn't finish in 1 s" in out


def test_a_grandchild_holding_doctors_output_open_doesnt_hang_the_hook(
    fake_doctor, monkeypatch, capsys
):
    """Like git's ssh or https helper outliving a stopped fetch: a pipe's read would wait for it."""
    fake_doctor(
        textwrap.dedent(
            """\
            import subprocess, time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            print(f"grandchild {child.pid}", flush=True)
            time.sleep(60)
            """
        ),
        deadline=1,
    )

    started = time.monotonic()
    out = start_up(monkeypatch, capsys)
    elapsed = time.monotonic() - started
    if pid := re.search(r"grandchild (\d+)", out):
        os.kill(int(pid[1]), signal.SIGTERM)

    assert pid, out
    assert elapsed < 15
    assert "doctor didn't finish in 1 s" in out


def script_block(path):
    """The inline `# /// script` metadata (PEP 723) at the top of a script."""
    lines = path.read_text("utf-8").splitlines()
    start = lines.index("# /// script") + 1
    end = lines.index("# ///", start)
    toml = "\n".join(line.removeprefix("#").removeprefix(" ") for line in lines[start:end])
    return tomllib.loads(toml)


def test_the_start_up_hook_installs_no_package_and_runs_the_repos_doctor():
    # A branch can't make every contributor's start-up install a package by editing the header.
    assert script_block(HOOKS / "start_doctor.py")["dependencies"] == []
    assert start_doctor.DOCTOR[1:] == [str(ROOT / "scripts" / "doctor.py"), "--check"]


def start_up_hook():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text("utf-8"))
    (entry,) = settings["hooks"]["SessionStart"]
    (hook,) = entry["hooks"]
    return entry["matcher"], hook


def test_doctor_runs_when_a_session_starts_not_on_resume_or_clear():
    matcher, hook = start_up_hook()

    assert matcher == "startup"
    assert "start_doctor.py" in hook["command"]
    # Room for uv's first download of Python; Claude Code drops all output after the timeout.
    assert hook["timeout"] == 90
    assert hook["timeout"] > start_doctor.DEADLINE


BASH = shutil.which("bash")


@pytest.mark.skipif(BASH is None, reason="Claude Code runs hook commands with bash")
def test_the_agent_is_told_to_install_uv_when_the_hook_cant_start(tmp_path):
    env = {"PATH": str(tmp_path), "CLAUDE_PROJECT_DIR": str(ROOT)}  # an empty folder: no uv
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]  # Git Bash needs it on Windows

    result = subprocess.run(
        [BASH, "-c", start_up_hook()[1]["command"]], env=env, capture_output=True, text=True,
        timeout=30,
    )  # fmt: skip

    assert result.returncode == 0
    assert "install uv" in result.stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repository standing in for the clone, with an ignored folder."""
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text("ignored/\n")
    monkeypatch.setattr(check_python, "ROOT", root)
    # Outside a uv project, `uv run --no-sync ruff` finds ruff in the active environment.
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    return root


def edit_python(path, source, monkeypatch):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return run_hook(check_python, {"file_path": str(path)}, monkeypatch)


@pytest.mark.parametrize("name", ["notes.txt", "ignored/scratch.py", "../outside.py"])
def test_ruff_runs_only_on_a_python_file_git_sees(name, repo, monkeypatch, capsys):
    # A ruff that ran would report a finding (exit 2): ruff lints an ignored file named to it.
    finding = [sys.executable, "-c", "import sys; print('E999', file=sys.stderr); sys.exit(1)"]
    monkeypatch.setattr(check_python, "CHECK", finding)

    assert edit_python(repo / name, "import os\n", monkeypatch) == 0
    assert capsys.readouterr().err == ""


def test_a_badly_formatted_file_is_formatted_without_telling_claude(repo, monkeypatch, capsys):
    path = repo / "app.py"

    assert edit_python(path, "name = 'Trayi'\n", monkeypatch) == 0
    assert path.read_text() == 'name = "Trayi"\n'
    assert capsys.readouterr().err == ""


def test_a_lint_finding_is_reported_to_claude_and_nothing_is_removed(repo, monkeypatch, capsys):
    path = repo / "app.py"
    source = "def total():\n    unused = 1\n    return 2\n"

    # No `--fix`: it would delete the variable, or an import, for Claude.
    assert edit_python(path, source, monkeypatch) == 2
    assert "F841" in capsys.readouterr().err
    assert path.read_text() == source


@pytest.mark.parametrize(
    "source",
    [
        "import os\n",  # the import first, its use in the next edit (F401)
        "print(os.sep)\n",  # the use first, its import in the next edit (F821)
    ],
)
def test_half_of_an_import_and_its_use_isnt_reported(source, repo, monkeypatch, capsys):
    """Each half of a two-edit change looks wrong alone; pre-commit still fails what's left."""
    path = repo / "app.py"

    assert edit_python(path, source, monkeypatch) == 0
    assert capsys.readouterr().err == ""
    assert path.read_text() == source


NO_RUFF = "import sys; print('Failed to spawn: ruff', file=sys.stderr); sys.exit(2)"


@pytest.mark.parametrize(
    "ruff",
    [
        [sys.executable, "-c", NO_RUFF],  # uv's exit before `uv sync` has installed ruff
        ["no-such-uv-anywhere"],  # uv itself missing
    ],
)
def test_a_ruff_that_cant_run_is_shown_to_the_person_only(ruff, repo, monkeypatch, capsys):
    monkeypatch.setattr(check_python, "FORMAT", ruff)
    monkeypatch.setattr(check_python, "CHECK", ruff)

    exit_code = edit_python(repo / "app.py", "x = 1\n", monkeypatch)

    err = capsys.readouterr().err
    assert exit_code == 1  # shown to the person, without waking Claude to "fix" the file
    assert "Couldn't run ruff" in err
    assert "found problems" not in err


def test_the_ruff_hook_runs_ruff_as_pre_commit_does():
    config = (ROOT / ".pre-commit-config.yaml").read_text("utf-8")
    check, format_check = re.findall(r"entry: (uv run --no-sync ruff .+)", config)

    # Less an import and its use, which can come in separate edits.
    assert check_python.CHECK == [*check.split(), "--ignore", "F401,F821"]
    # It formats the file rather than failing on it.
    assert check_python.FORMAT == [arg for arg in format_check.split() if arg != "--check"]


def test_the_ruff_hook_runs_after_each_edit_of_a_python_file():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text("utf-8"))
    hooks = [hook for entry in settings["hooks"]["PostToolUse"] for hook in entry["hooks"]]

    ruff_hooks = [hook for hook in hooks if "check_python.py" in hook["command"]]

    assert {hook["if"] for hook in ruff_hooks} == {"Edit(*.py)", "Write(*.py)"}
    assert not any(hook.get("async") or hook.get("asyncRewake") for hook in ruff_hooks)

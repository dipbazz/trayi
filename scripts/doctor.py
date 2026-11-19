#!/usr/bin/env -S uv run --script
# /// script
# # Its own environment in uv's cache, never .venv, so it can rebuild a .venv on Windows.
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Check a clone of Trayi before you, or your AI agent, start work on it.

Run it with `uv run --script scripts/doctor.py` (no uv yet? `python3 scripts/doctor.py`, or
`py scripts/doctor.py` on Windows, tells you how to get it). It prints one line per check: ✓, ⚠️
(a warning, with its fix) or ❌ (an error, with its fix). Getting started explains it
(docs/getting-started/index.md).

It only reports: it never pulls, checks out, resets, runs `migrate` or installs hooks. Its one
change is `uv sync --locked --group docs`, which brings `.venv` in line with `uv.lock`;
`--check` (the start-up hook's mode) only checks whether that's needed.

Exit codes:
  0  nothing to fix (warnings may have printed)
  1  at least one ❌
  2  doctor couldn't check: git is missing, this file isn't in a git clone, or Python is older
     than 3.14

Standard library only, and the guard below parses on old Pythons, so it can say what's missing.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 14):
    print(
        "doctor needs Python 3.14, which uv installs for you: install uv "
        "(https://docs.astral.sh/uv/getting-started/installation/), "
        "then run `uv run --script scripts/doctor.py`"
    )
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
UV_INSTALL = "https://docs.astral.sh/uv/getting-started/installation/"
MIN_UV = (0, 6, 10)  # the first uv with `uv sync --check`
SYNC = ["sync", "--locked", "--group", "docs"]  # the same as docs/getting-started/index.md
FETCH_TIMEOUT = 20  # seconds
TRAYI = "https://github.com/dipbazz/trayi.git"
TRAYI_URL = re.compile(
    r"(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com(?::22)?/)"
    r"dipbazz/(?:trayi|charity-wagtail-cms)(?:\.git)?/?",
    re.IGNORECASE,
)
OK, WARN, FAIL = "✓", "⚠️", "❌"
COLOURS = {OK: "\x1b[32m", WARN: "\x1b[33m", FAIL: "\x1b[31m"}


def which(name):
    return shutil.which(name)


def uv_command():
    """How to call uv, or None when it isn't installed."""
    path = which("uv")
    return [path] if path else None


def stdout_is_terminal():
    return sys.stdout.isatty()


def run(args, cwd, env=None, timeout=None):
    """Run a command; return (exit code, stdout, stderr).

    Output goes to temporary files, not pipes: on Windows a child that outlives a timed-out
    command (git's ssh or https helper) would hold a pipe open and hang the read.
    """
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        result = subprocess.run(
            args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            timeout=timeout,
        )  # fmt: skip
        out.seek(0)
        err.seek(0)
        return (
            result.returncode,
            out.read().decode("utf-8", "replace").strip(),
            err.read().decode("utf-8", "replace").strip(),
        )


def git(root, *args, env=None, timeout=None):
    return run(["git", *args], cwd=root, env=env, timeout=timeout)


def last_line(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "no message"


class Report:
    def __init__(self, root, check):
        self.root = root
        self.check = check
        self.colour = stdout_is_terminal() and not os.environ.get("NO_COLOR")
        self.failed = False
        self.uv = None

    def line(self, level, text):
        if level == FAIL:
            self.failed = True
        symbol = f"{COLOURS[level]}{level}\x1b[0m" if self.colour else level
        print(f"{symbol} {text}", flush=True)


# The checks, run in this order (CHECKS at the end). Each prints its own lines.


def check_uv(report):
    report.uv = uv_command()
    if not report.uv:
        report.line(FAIL, f"uv isn't installed: install it from {UV_INSTALL}")
        return
    _, out, err = run([*report.uv, "--version"], cwd=report.root)
    found = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    minimum = ".".join(map(str, MIN_UV))
    if not found:
        text = last_line(out or err)
        report.line(WARN, f"couldn't read uv's version from {text!r}; Trayi needs {minimum}+")
        return
    version = tuple(int(part) for part in found.groups())
    if version < MIN_UV:
        report.line(
            FAIL,
            f"uv {found.group(0)} is too old; Trayi needs {minimum} or newer: run "
            "`uv self update` (or update uv the way you installed it)",
        )
        return
    report.line(OK, f"uv {found.group(0)}")


def check_identity(report):
    missing = [key for key in ("name", "email") if not git(report.root, "config", f"user.{key}")[1]]
    if missing:
        report.line(
            FAIL,
            f"git doesn't know your {' and '.join(missing)}: run "
            + " and ".join(
                f'`git config --global user.{key} "Your {key.title()}"`' for key in missing
            ),
        )
        return
    report.line(OK, "git name and email set")


def is_trayi_url(url):
    return bool(TRAYI_URL.fullmatch(url.strip()))


def trayi_remote(root):
    """The name of the remote whose address is github.com/dipbazz/trayi, or None."""
    _, out, _ = git(root, "config", "--get-regexp", r"^remote\..*\.url$")
    names = []
    for entry in out.splitlines():
        key, _, url = entry.partition(" ")
        if is_trayi_url(url):
            names.append(key.removeprefix("remote.").removesuffix(".url"))
    for preferred in ("upstream", "origin"):
        if preferred in names:
            return preferred
    return names[0] if names else None


def fetch_env(root):
    """An environment in which git fails instead of asking for a password or passphrase."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    has_own_ssh = (
        "GIT_SSH_COMMAND" in env
        or "GIT_SSH" in env
        or git(root, "config", "core.sshCommand")[0] == 0
    )
    if not has_own_ssh:
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    return env


def check_upstream(report):
    root = report.root
    remote = trayi_remote(root)
    if not remote:
        report.line(
            WARN,
            "no remote points at github.com/dipbazz/trayi, so doctor can't tell if your code "
            f"is up to date: run `git remote add upstream {TRAYI}`",
        )
        return
    try:
        code, _, err = git(
            root, "fetch", "--quiet", "--no-tags", remote, "main",
            env=fetch_env(root), timeout=FETCH_TIMEOUT,
        )  # fmt: skip
        problem = last_line(err) if code else None
    except subprocess.TimeoutExpired:
        problem = f"no answer in {FETCH_TIMEOUT} s"
    if problem:
        report.line(WARN, f"couldn't fetch {remote} ({problem}): comparing with your last fetch")
    upstream = f"{remote}/main"
    code, behind, _ = git(root, "rev-list", "--count", f"HEAD..refs/remotes/{upstream}")
    if code:
        report.line(WARN, f"{upstream} isn't fetched yet: run `git fetch {remote}`")
        return
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD")[1] or "HEAD (detached)"
    count = int(behind)
    commits = f"{count} commit{'' if count == 1 else 's'}"
    if count == 0:
        report.line(OK, f"{branch} is up to date with {upstream}")
    elif branch == "main":
        report.line(
            FAIL, f"main is {commits} behind {upstream}: run `git pull --ff-only {remote} main`"
        )
    else:
        report.line(
            WARN, f"{branch} is {commits} behind {upstream}: rebase or merge it when you're ready"
        )


def check_dependencies(report):
    if not report.uv:
        report.line(WARN, "dependencies not checked: install uv first")
        return
    args = [*SYNC, "--check"] if report.check else SYNC
    code, _, err = run([*report.uv, *args], cwd=report.root)
    command = " ".join(["uv", *SYNC])
    if code == 0:
        report.line(OK, "dependencies match uv.lock")
    elif "os error 32" in err:
        report.line(
            WARN,
            ".venv is in use by another program (runserver or your editor?): stop it, "
            "then run doctor again",
        )
    elif report.check:
        report.line(FAIL, f"dependencies out of date: run `{command}`")
    else:
        report.line(FAIL, f"`{command}` failed: {last_line(err)}")


def hook_types(root):
    """The hooks `pre-commit install` sets up, from .pre-commit-config.yaml."""
    try:
        config = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    except OSError:
        return ["pre-commit"]
    # YAML's one-line `[a, b]` or its `- a` list on the lines below.
    flow = re.search(r"^default_install_hook_types:[ \t]*\[([^\]]*)\]", config, re.MULTILINE)
    block = re.search(
        r"^default_install_hook_types:[ \t]*(?:#.*)?\n((?:[ \t]*-[^\n]*\n?)+)", config, re.MULTILINE
    )
    if flow:
        names = flow.group(1).split(",")
    elif block:
        items = block.group(1).splitlines()
        names = [item.split("#")[0].strip().removeprefix("-") for item in items]
    else:
        return ["pre-commit"]
    return [name.strip().strip("'\"") for name in names if name.strip()]


def is_pre_commit_hook(path):
    try:
        with path.open(encoding="utf-8", errors="replace") as hook:
            head = [hook.readline() for _ in range(5)]
    except OSError:
        return False
    return any("generated by pre-commit" in text for text in head)


def check_hooks(report):
    _, hooks, _ = git(report.root, "rev-parse", "--git-path", "hooks")
    folder = report.root / hooks  # an absolute core.hooksPath replaces the root
    types = hook_types(report.root)
    missing = [name for name in types if not is_pre_commit_hook(folder / name)]
    if missing:
        report.line(
            FAIL,
            f"pre-commit hooks missing ({', '.join(missing)}): run `uv run pre-commit install`",
        )
        return
    report.line(OK, f"pre-commit hooks installed ({', '.join(types)})")


def check_database(report):
    if not (report.root / "db.sqlite3").exists():
        # `migrate --check` would create an empty database.
        report.line(FAIL, "no database yet: run `uv run python manage.py migrate`")
        return
    if not report.uv:
        report.line(WARN, "migrations not checked: install uv first")
        return
    env = dict(os.environ, DJANGO_SETTINGS_MODULE="charity.settings.dev")
    code, _, err = run(
        [*report.uv, "run", "--no-sync", "python", "manage.py", "migrate", "--check"],
        cwd=report.root,
        env=env,
    )
    if code == 0:
        report.line(OK, "migrations applied")
    elif "Traceback" in err:
        report.line(FAIL, f"Django couldn't start: {last_line(err)}")
    else:
        report.line(FAIL, "migrations not applied: run `uv run python manage.py migrate`")


CHECKS = [check_uv, check_identity, check_upstream, check_dependencies, check_hooks, check_database]


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description="Check a clone of Trayi before work starts.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="never run `uv sync`; only say whether it's needed (the start-up hook's mode)",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = Report(root, args.check)
    if not which("git"):
        report.line(FAIL, "git isn't installed: install git 2.31 or newer, then run doctor again")
        return 2
    code, inside, _ = git(root, "rev-parse", "--is-inside-work-tree")
    if code or inside != "true":
        report.line(FAIL, f"{root} isn't a git clone: clone {TRAYI} and run doctor from there")
        return 2
    for check in CHECKS:
        try:
            check(report)
        except Exception as error:  # one broken check mustn't hide the others
            report.line(FAIL, f"doctor couldn't run this check: {error}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())

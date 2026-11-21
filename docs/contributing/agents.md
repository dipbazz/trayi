# Working with an AI agent

An AI agent (Claude Code, Codex, GitHub Copilot or another) follows the same workflow as a person
([Contributing](index.md#the-workflow)). Most tools read `AGENTS.md` at the root first: a short
page that points here. Claude Code reads `CLAUDE.md`, which pulls in `AGENTS.md` with its
`@AGENTS.md` line and adds only what's particular to Claude Code. The two together stay under
600 words (a pre-commit check), so new rules for agents go on this page, with a one-line pointer
in `AGENTS.md` when every session needs it.

## At the start of a session

1. **Run doctor:** `uv run --script scripts/doctor.py` (install [uv](https://docs.astral.sh/uv/)
   first). Fix each ❌ before other work; it says how ([Getting started](../getting-started/index.md)).
2. **Read `docs/project-context.md`**, the map of which page answers which question.
3. **Fetch before comparing.** Before reading code to compare it with `main`, or reviewing a pull
   request, fetch Trayi's `main` and compare against it: `git fetch upstream` then
   `upstream/main` on a fork, `origin` on a clone of Trayi itself. A local `main` can be weeks
   old.

## What an agent does without asking

- Read the code and the docs, run doctor, the tests for the code it touched, and the docs build.
- Fetch, and fast-forward its local `main` (`git pull --ff-only upstream main`, or `origin`).
- Branch from `main` for its issue and commit there, one logical change per commit
  ([Commits](index.md#commits)).
- Post a review's comment when it's asked to do the review, and re-run a pull request's
  `Reviews` check after a person has removed a `needs:` label.

## What it asks before

By default an agent asks before it:

- pushes a branch or opens a pull request;
- posts on an issue or pull request, files an issue or changes a label, other than the review
  comment above;
- rewrites a branch it has already pushed.

A contributor can loosen these for their own agent ([below](#overriding-the-defaults)).

## What it never does

No local file changes these. CI and the maintainer hold to them whatever an agent is told:

- **Merge a pull request.** The maintainer merges ([Contributing](index.md#the-workflow), step 10).
- **Remove a `needs:` label.** A person removes it after reading the review's comment
  ([Reviews](reviews.md)).
- **Skip a review or a check**, such as committing with `--no-verify`.
- **Work on a stale `main`**: it fetches first, as above.

## When it makes a mistake

An agent that finds a mistake of its own, such as a wrong claim in a commit message, a test it
broke or a command that did more than it meant, says so before it fixes anything: what went
wrong, why, and how it would fix it. A fix that rewrites a pushed branch, gets round a check or
changes something other people use waits for the person's yes ([above](#what-it-asks-before)).
If a check or setting should have stopped an action and didn't, it says that too, so the gap
can be closed. A mistake fixed quietly is easy to miss, and the next fix is then built on it.

## What "done" means

A pull request is done when every step of [the workflow](index.md#the-workflow) is: tests
written first and passing for the code it touched ([Testing](testing.md)), the docs pages it
describes updated and building with `-W` ([Writing docs](writing-docs.md)), a changelog file or
the `no changelog` label, and a "Check before merging" section with a box per page and width, or
saying nothing needs checking. An agent that can't finish a step says which and why in the pull
request, rather than leaving it out.

## Overriding the defaults

Each tool reads its own personal file, and `.gitignore` keeps each out of git, so an override
stays on your machine:

| Tool | Instructions (such as "push without asking") | Permissions |
|---|---|---|
| Claude Code | `CLAUDE.local.md` | `.claude/settings.local.json` |
| Codex | `AGENTS.override.md` | Codex's own settings |
| GitHub Copilot | None inside the repo: your editor's or GitHub account's settings | The same |

An override can change what an agent asks before; it can't change what it never does.

## Working from a fork

Without write access to Trayi, work from a fork: see
[Working from a fork](index.md#working-from-a-fork). Doctor and the steps above use the
`upstream` remote it adds.

## Someone else's branch

Before starting an agent on another person's branch, such as a pull request from a fork, read
the diff of the files that run code on your machine:
[Security](security.md#read-a-branchs-tooling-before-running-it).

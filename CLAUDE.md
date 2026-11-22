@AGENTS.md

## Claude Code

Load the `workflow` skill to file an issue, start one, open a pull request or finish a review.
Load the `mobile-first` skill before writing or reviewing any CSS or layout markup.

## Where rules live

Rules say what, when and where; memory says who, which and how. A rule for every contributor goes
in `docs/`, with a short pointer in a skill (`.claude/skills/`, loaded by task) or a rule file
(`.claude/rules/<topic>.md` with `paths:` frontmatter, loaded when a matching file is opened). A
rule a machine can check is a check instead: CI, pre-commit, or a hook in `.claude/settings.json`.
A rule for this maintainer alone goes in `CLAUDE.local.md`. Memory holds only current state and
how-to for this machine. When a workflow or decision comes up that none of these covers, first
propose where it goes, get the user's yes, and write it there before relying on it.

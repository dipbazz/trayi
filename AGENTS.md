# Trayi

Install [uv](https://docs.astral.sh/uv/) first, then run `uv run --script scripts/doctor.py`
before other work. What an agent does without asking, what it never does and what "done" means
are in `docs/contributing/agents.md`.

The documentation is in `docs/` (Sphinx with MyST Markdown; plain Markdown you can read
directly). Read `docs/project-context.md` before exploring the code: a one-page map of which
docs page answers which question. Catch up with `git log --oneline <version>..HEAD --stat`,
where `<version>` is that page's "Last verified against". A PR that changes what a docs page
describes updates that page in the same PR, and the docs must build with
`uv run --group docs sphinx-build -W --keep-going docs docs/_build/html`.

## Every charity, standard first

Many charities run this one product, each on its own installation on a shared server; never build
several into one (`docs/decisions.md`), and never offer a template, CSS, code or branch for one
charity only. Before proposing a fix, feature or design, answer the questions in the Principles
section of `docs/contributing/index.md` in the proposal. Follow the standards (WCAG 2.2 AA, web
conventions, `docs/site/standard.md`, the law) before modern styling, and add modern styling only
through the design tokens and shared components.

## Reviews before code and before merge

A `needs: …` label marks a review an issue or pull request still owes
(`docs/contributing/reviews.md`); an issue's reviews come before branching, and CI fails a pull request
while one is left. Before each commit, check the change belongs to this branch's issue; if not,
branch from `main` for it.

## Versions and changelog

Every PR adds a file `changelog.d/<slug>.<group>.md` (the entry, written for the person the change
affects), or is labelled `no changelog` (CI checks this). Only a release edits `CHANGELOG.md`. Put
a PR in the milestone of the issue it closes; which milestone new work joins, and the release
steps, are in `docs/contributing/releases.md`; it also says which release is 1.0.0.

## Design mobile first

Start from semantic HTML, style a 320px phone with no media query, then add `min-width` queries
in `rem`; never override down with `max-width`.

## QA is part of done

Run only the tests you wrote or changed and those for the code you touched
(`docs/contributing/testing.md`, "Running the tests"); CI runs the whole suite, including the
layout checks at six widths. Fix each bug test-first, one bug per commit; if pytest can't catch
it, say so in the pull request. The pull request's "Check before merging" section has a `- [ ]`
box per page and width with what to look for, or says nothing needs checking.

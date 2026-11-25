---
name: workflow
description: How this project runs its reviews with gstack and Claude Code, label by label. Use when filing an issue, starting work on an issue, opening a pull request, finishing a review, or when the last issue of a milestone closes; and whenever asked which issues or pull requests need a review.
---

# Workflow: reviews and their labels

`docs/contributing/reviews.md` is the source for which review an issue or pull request needs, the
command that runs it, the order, and when a label comes off; `docs/contributing/index.md`, "The
workflow", is the source for every step from issue to merge. Read them first. This skill adds
only what's particular to running them with Claude Code and gstack.

## Find what's waiting

Never scan every issue to answer "what needs a review?": run the label commands in
`docs/contributing/reviews.md`, "Find what's waiting", and list titles only.

## Filing an issue

File, tier and label it as `docs/contributing/releases.md`, "Issues", and
`docs/contributing/reviews.md`, "Tiers: how much review a change gets", say. Then tell the user
in one line each which labels you added and why.

## Starting an issue

Run `gh issue view <n> --json labels` first. A `needs:` label's review comes before the branch
(`docs/contributing/reviews.md`, "Which reviews an issue or pull request needs"). If the gstack
skill it names isn't installed, stop and tell the user to install gstack
(`docs/contributing/reviews.md`, "Tools"); never skip the review. Then branch as
`docs/contributing/index.md`, "The workflow", step 2 says.

| Review | Particular to gstack here |
|---|---|
| design | The design system is the tokens in `charity.css`, the `mobile-first` skill and `docs/site/standard.md`; there's no DESIGN.md. Skip AI image mockups. |
| eng | Its test plan feeds `/qa-only` later. |
| investigation | `/investigate` writes the fix and the test together: see the test fail without the fix, then commit them, one bug per commit. |

For every gstack review: decline its copy into `docs/designs/` and its TODOS.md entries (deferred
work becomes a GitHub issue), and keep the full report in `~/.gstack`.

## Finishing a review

Follow `docs/contributing/reviews.md`, "When a review is done": green CI first, one comment where
the label is, and the label left for a person. Then:

1. Ask the user to remove the label, from the place you commented. Once they've removed an
   issue's label, re-run the `Reviews` check of any open pull request that closes it:
   `gh run rerun` on its latest `Reviews` run.
2. Suggest `/clear` before the next review or the build: the comment carries the decisions.

## Opening a pull request

Straight after opening it, check what `docs/contributing/index.md`, "The workflow", step 7 lists,
then anything your own `CLAUDE.local.md` adds.

Before running a review asked for by name, check `gh pr view <n> --json labels` and the existing
review comments. If its label is gone, or an earlier review it depends on is still owed
(`docs/contributing/reviews.md`, "Which reviews an issue or pull request needs"), say so and ask
before running it.

- **Code review:** Claude Code's `/code-review`, not gstack's `/review`. Fix its findings
  yourself, test-first, never with `--fix`.
- **QA:** `/qa-only`, never `/qa` or `/design-review`: those commit their own fixes, several per
  commit.

## When a milestone's last issue closes

Suggest cutting the release (`docs/contributing/releases.md`, "Cutting a release"). With
`/canary` on the live site, decline its rollback option: deploys go by tag.

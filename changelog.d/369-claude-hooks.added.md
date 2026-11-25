Contributors using Claude Code get more checks without asking for them: a new session starts by
running `scripts/doctor.py --check` and showing its lines, each Python file Claude Code edits is
formatted with ruff and its lint findings reported straight away, and every Claude Code (not only
the maintainer's) is reminded that a review ends with one comment where its label is, the label
left for a person. The two hooks that were already there, the one that stops a whole-suite test
run and the stylesheet check, no longer block a prompt or tool when they can't start, and no
longer fail on Nepali text on Windows. The workflow skill now keeps only Claude Code's own steps
and points into the docs for the rest ([#369](https://github.com/dipbazz/trayi/issues/369)).

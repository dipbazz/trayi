"""Remind Claude Code how a label review ends.

A UserPromptSubmit hook, and a PreToolUse hook on Skill (.claude/settings.json). Asking for a
review ("run code review on 323", "/qa-only"), or Claude starting a review skill itself, adds a
reminder to load the `workflow` skill and to finish the review where its label is: one comment,
then the person asked to remove the label (docs/contributing/reviews.md, "When a review is
done"). A finding report alone doesn't finish it: PR #323's review ran with /code-review alone,
and its comment and label were nearly forgotten.

Shown once a session: a marker file in the temp folder, named after the session, stops it
repeating.
"""

import json
import re
import sys
import tempfile
from pathlib import Path

# The commands in reviews.md's "Run with" column, less /office-hours (it shapes a raw idea before
# any label asks for a review), plus Claude Code's own /security-review, which people type for a
# security review. core/tests/test_claude_hooks.py keeps the two in step.
REVIEW_SKILLS = frozenset(
    {
        "code-review",
        "cso",
        "investigate",
        "plan-ceo-review",
        "plan-design-review",
        "plan-eng-review",
        "qa-only",
        "security-review",
    }
)
# A request to run one, not a mention: a review command; a verb like "run" or "start" up to
# three words before "<kind> review" or "investigation"; "<kind> review" or "QA" right before a
# number; "QA review"; or a `needs:` label. "...not be missed by the design review" (8 Nov) is a
# mention. A request these miss is still caught when Claude starts the review skill (PreToolUse).
# Mentions that matched once, each using up the once-a-session reminder: a command inside a path
# (".claude/skills/code-review/"), a verb in the sentence before ("Did you run it? The code
# review comment..."), a report ("the code review of 323 found...") and "QA for 6 widths".
KIND = r"(?:code|security|design|eng|product|qa)[- ]review"
COMMANDS = "|".join(re.escape(skill) for skill in sorted(REVIEW_SKILLS))
REVIEW_WORDS = re.compile(
    rf"(?<![\w/.:-])/(?:{COMMANDS})(?![\w/-])"
    rf"|\b(?:run|do|start|begin|finish|continue|time for|let'?s)\b(?:\s+[^\s.?!;]+){{0,3}}?"
    rf"\s+(?:{KIND}|investigation)\b"
    rf"|\b{KIND}\s+(?:on\s+|for\s+)?#?\d+"
    rf"|needs:\s*(?:{KIND}|qa|investigation)\b"
    r"|\bqa[- ]review\b"
    r"|\bqa\s+(?:on\s+#?\d+|for\s+#\d+|#?\d+)|\b(?:run|do|start)\s+(?:the\s+)?qa\b",
    re.IGNORECASE,
)
REMINDER = (
    "This is a label review (docs/contributing/reviews.md). Load the `workflow` skill before"
    " running it, if it isn't loaded: it gives the label, the order and the command. It isn't"
    " finished until its result is one comment where the label is (format in reviews.md, 'When a"
    " review is done') and the person has been asked to remove the label: agents never remove a"
    " `needs:` label (docs/contributing/agents.md). A finding report alone doesn't finish it."
)
MARKERS = Path(tempfile.gettempdir())


def asks_for_a_review(hook):
    if hook.get("hook_event_name") == "PreToolUse":
        skill = (hook.get("tool_input") or {}).get("skill", "")
        return skill.split(":")[-1] in REVIEW_SKILLS  # gstack's skills come as gstack:<name>
    return bool(REVIEW_WORDS.search(hook.get("prompt", "")))


def first_time(session_id):
    """True the first time a session asks; True too when the marker can't be written."""
    # Claude Code sends a UUID; keeping only its characters stops a "/../" leaving MARKERS.
    name = re.sub(r"[^A-Za-z0-9-]", "", str(session_id)) or "none"
    marker = MARKERS / f"review-workflow-{name}"
    if marker.exists():
        return False
    try:
        marker.touch()
    except OSError:
        pass  # better shown twice in a session than not at all
    return True


def main():
    try:
        # The bytes, as UTF-8: Python on Windows reads text stdin in the ANSI code page.
        hook = json.load(sys.stdin.buffer)
    except ValueError:
        return 0
    if not asks_for_a_review(hook) or not first_time(hook.get("session_id", "none")):
        return 0
    if hook.get("hook_event_name") == "PreToolUse":
        context = {"hookEventName": "PreToolUse", "additionalContext": REMINDER}
        print(json.dumps({"hookSpecificOutput": context}))
    else:
        print(REMINDER)  # a UserPromptSubmit hook's output reaches Claude as context
    return 0


if __name__ == "__main__":
    sys.exit(main())

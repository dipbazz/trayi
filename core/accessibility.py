"""The platform's part of every site's accessibility statement (#167): how well the site works,
how that's checked, and what doesn't work yet, the same for every charity.

The code has no release date, so each release checks this list and moves `REVIEWED` to the day
it was checked (`docs/contributing/releases.md`). A problem fixed in a release comes off the list
in the same pull request as the fix.
"""

from datetime import date

from django.utils.translation import gettext_lazy as _

# The page type each home page has one of, as ("app_label", "model") so `core` imports nothing
# from `home`.
STATEMENT_PAGE_TYPE = ("home", "accessibilitystatementpage")

REVIEWED = date(2026, 11, 13)

# What every change to the code is checked for before it's released.
CHECKS = (
    _("text and buttons have enough colour contrast, whatever colours the charity chooses"),
    _("everything you can reach with the Tab key shows clearly where you are"),
    _("everything you tap is at least 44 pixels tall"),
    _("every kind of page fits screens from 320 pixels wide without scrolling sideways"),
    _("a person checks each page the change affects, on a phone and on a wide screen"),
)

KNOWN_PROBLEMS = (
    _(
        "The page that asks for a password, or for you to log in, before you can read a private "
        "page doesn't look like the rest of the site, and on a phone its text is small until you "
        "zoom in."
    ),
    _(
        "With a contrast theme turned on, such as Windows' contrast themes, buttons look like "
        "plain text and an appeal's progress bar disappears."
    ),
    _(
        "On a wide screen, the lines of an appeal's story, and of other pages, are longer than is "
        "comfortable to read."
    ),
)

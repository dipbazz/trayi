"""The menu's standard sections (#171): which page each one is, and which the menu leaves out.

The sections, their order and their names come from the standard (`docs/site/standard.md`, "The
menu"), never from page titles: a moderator only chooses which page each one links to, in Site
settings → Menu. The menu tag and the Menu tab both read `menu_sections`, so what the tab says is
left out is what the menu leaves out.
"""

from dataclasses import dataclass

from django.db.models import CharField, Exists, ExpressionWrapper, F, OuterRef
from django.utils import translation
from django.utils.text import get_text_list
from django.utils.translation import gettext_lazy as _
from wagtail.models import PageViewRestriction

SHOWN = "shown"
NOT_SET = "not set"
NOT_PUBLISHED = "not published"
NOT_PUBLIC = "not public"


@dataclass(frozen=True)
class Section:
    """`setting` is its chooser on SiteSettings and `name` the menu's, translated. `page_type` is
    the one kind of page it takes, as an "app_label.model" label so `core` imports nothing from the
    feature apps, or "" for any; `wrong_type` is the admin's error for another kind, in English as
    the rest of the admin's own messages are."""

    setting: str
    name: str
    page_type: str = ""
    wrong_type: str = ""

    @property
    def admin_name(self):
        """Its name in the admin's own messages, in English even on a site that opens in another
        language."""
        with translation.override("en"):
            return str(self.name)


SECTIONS = (
    Section("about_page", _("About us")),
    Section(
        "appeals_page",
        _("Appeals"),
        "campaigns.campaignindexpage",
        "Choose the appeals page: Appeals lists its appeals.",
    ),
    Section(
        "stories_page",
        _("Stories"),
        "news.newsindexpage",
        "Choose the stories page: Stories lists its stories.",
    ),
    Section("get_involved_page", _("Get involved")),
    Section(
        "contact_page",
        _("Contact"),
        "contact.contactpage",
        "Choose the Contact page: it holds the message form.",
    ),
)

# The other chooser that takes one kind of page: the header's Donate button.
DONATE = Section(
    "donate_page",
    _("Donate"),
    "campaigns.donatepage",
    "Choose the Donate page: it holds the pledge form.",
)


@dataclass(frozen=True)
class MenuSection:
    """A section, the page it links to in the language being read, and whether it's shown."""

    section: Section
    page: object
    status: str

    @property
    def name(self):
        return self.section.name


def with_privacy(pages):
    """`pages`, a Page queryset, each with `private`: whether it's behind a password, a login or
    a group, or under a page that is. Read in the same query as the pages."""
    page_path = ExpressionWrapper(OuterRef("path"), output_field=CharField())
    over_it = PageViewRestriction.objects.annotate(page_path=page_path).filter(
        page_path__startswith=F("page__path")
    )
    return pages.annotate(private=Exists(over_it))


def chosen_status(page):
    """Whether a page chosen in settings is linked to: SHOWN while it's live and public, as public
    listings are (`.live().public()`), else why not. `page` is read `with_privacy`, or None."""
    if page is None or not page.live:
        return NOT_PUBLISHED
    if page.private:
        return NOT_PUBLIC
    return SHOWN


def link_to(page, translation):
    """The page a link to `page`, chosen in settings, goes to in the language being read, or None.

    Only the chosen page decides whether there's a link, in every language (`chosen_status`), so
    the admin, which reads only the chosen pages, says what each language's site does. The link
    goes to `translation`, its translation in the language being read, while that's live and
    public, else to the chosen page. Both are read `with_privacy`.
    """
    if chosen_status(page) != SHOWN:
        return None
    if translation is not None and chosen_status(translation) == SHOWN:
        return translation
    return page


def menu_sections(site_settings, chosen, translated):
    """Each section, in the standard's order, with the page it links to and its status.

    `chosen` maps a section's setting to its chosen page, or None, and `translated` to that page's
    translation in the language being read, or None; the link is `link_to` them.
    """
    sections = []
    for section in SECTIONS:
        page = chosen.get(section.setting)
        if getattr(site_settings, f"{section.setting}_id") is None:
            status = NOT_SET
        else:
            status = chosen_status(page)
        link = link_to(page, translated.get(section.setting))
        sections.append(MenuSection(section, link, status))
    return sections


# A home page's depth in the tree, under the root: a section's page is below one, since the
# site's name links to the home page and a home page holds every page of its site.
HOME_DEPTH = 2


def wrong_choices(site_settings):
    """Errors for SiteSettings.clean(), by field: a page chosen for two sections, on each of
    them, a home page, and a page of the wrong kind for a chooser that takes one kind."""
    errors = {}
    # By translation key: a page and its translations are one page in each language.
    by_page = {}
    for section in (*SECTIONS, DONATE):
        page = getattr(site_settings, section.setting)
        if page is None:
            continue
        model = page.specific_class
        if section.page_type and (model is None or model._meta.label_lower != section.page_type):
            errors[section.setting] = section.wrong_type
        elif section is not DONATE and page.depth <= HOME_DEPTH:
            errors[section.setting] = (
                "Choose a page under the home page: the site's name links to it already."
            )
        elif section is not DONATE:
            by_page.setdefault(page.translation_key, []).append(section)
    for sections in by_page.values():
        if len(sections) < 2:
            continue
        names = get_text_list([section.admin_name for section in sections], "and")
        rest = "another page for the other" if len(sections) == 2 else "other pages for the others"
        for section in sections:
            errors[section.setting] = (
                f"{names} link to the same page. Keep it on one and choose {rest}."
            )
    return errors

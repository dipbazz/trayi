from django.db.models import Q
from django.utils.functional import SimpleLazyObject
from wagtail.models import Page

from core.languages import reading_language
from core.menu import SECTIONS, SHOWN, link_to, menu_sections, with_privacy
from core.models import AnnouncementBanner, SiteSettings


def chosen_pages(request):
    """The pages chosen in settings that every page links to, in the language being read.

    `privacy_page` is the privacy notice for the footer and forms (#105) and `donate_page_link` the
    header's Donate button, and `banner_link_page` the announcement banner's link (#117).
    `menu_sections` are the menu's sections that have a page, in the standard's order (#171), and
    `contact_page_link` the footer's Contact link, their Contact page or None (#167). Each links
    as the menu does (`link_to`): only while the chosen page is published and public, so nothing
    links to a draft or a page behind a password (#312), and then to its published, public
    translation in the language being read, else to the chosen page.

    Looked up only when a template uses one, and then all together in one query: the chosen pages
    and their published translations in the language being read, each with whether it's behind a
    password or login.
    """

    def find():
        site_settings = SiteSettings.for_request(request)
        banner = AnnouncementBanner.for_request(request)
        chosen = {
            "privacy_page": site_settings.privacy_page_id,
            "donate_page_link": site_settings.donate_page_id,
            "banner_link_page": banner.link_page_id if banner.enabled else None,
        }
        for section in SECTIONS:
            chosen[section.setting] = getattr(site_settings, f"{section.setting}_id")
        pages, translated = find_in_reading_language(chosen)
        found = {
            name: link_to(pages[name], translated[name])
            for name in ("privacy_page", "donate_page_link", "banner_link_page")
        }
        found["menu_sections"] = [
            section
            for section in menu_sections(site_settings, pages, translated)
            if section.status == SHOWN
        ]
        found["contact_page_link"] = next(
            (s.page for s in found["menu_sections"] if s.section.setting == "contact_page"), None
        )
        return found

    def find_in_reading_language(chosen):
        """Each chosen page, by name, and its published translation in the language being read."""
        ids = {pk for pk in chosen.values() if pk is not None}
        if not ids:
            return dict.fromkeys(chosen), dict.fromkeys(chosen)
        language = reading_language()
        pages = with_privacy(
            Page.objects.filter(
                Q(pk__in=ids)
                | Q(
                    translation_key__in=Page.objects.filter(pk__in=ids).values("translation_key"),
                    locale__language_code=language,
                    live=True,
                )
            )
        ).select_related("locale")
        by_id = {page.pk: page for page in pages}
        translations = {
            page.translation_key: page
            for page in by_id.values()
            if page.locale.language_code == language and page.live
        }
        pages = {name: by_id.get(pk) for name, pk in chosen.items()}
        translated = {
            name: translations.get(page.translation_key) if page is not None else None
            for name, page in pages.items()
        }
        return pages, translated

    pages = SimpleLazyObject(find)
    names = (
        "privacy_page",
        "donate_page_link",
        "banner_link_page",
        "menu_sections",
        "contact_page_link",
    )
    return {name: SimpleLazyObject(lambda name=name: pages[name]) for name in names}

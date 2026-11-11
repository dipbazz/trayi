import datetime

import pytest
from bs4 import BeautifulSoup
from wagtail.models import PageViewRestriction

from contact.models import ContactPage
from core import accessibility
from core.models import SiteSettings
from home.models import AccessibilityStatementPage, StandardPage

pytestmark = pytest.mark.django_db


def add_statement(parent, **fields):
    statement = AccessibilityStatementPage(
        title=fields.pop("title", "Accessibility statement"), slug="accessibility", **fields
    )
    parent.add_child(instance=statement)
    statement.save_revision().publish()
    return statement


def section(client, heading, path="/accessibility/"):
    """The text under the H2 `heading`, up to the next H2, or None if there's no such H2."""
    page = BeautifulSoup(client.get(path).content, "html.parser")
    h2 = next((h2 for h2 in page.select("main h2") if h2.get_text(strip=True) == heading), None)
    if h2 is None:
        return None
    return h2.find_parent("section")


@pytest.fixture
def known_problems(monkeypatch):
    monkeypatch.setattr(accessibility, "KNOWN_PROBLEMS", ("The map doesn't zoom.",))
    monkeypatch.setattr(accessibility, "REVIEWED", datetime.date(2026, 11, 11))


class TestPageTreeRules:
    def test_lives_under_the_home_page_only(self, home_page):
        about = StandardPage(title="About us")
        home_page.add_child(instance=about)

        assert AccessibilityStatementPage.can_create_at(home_page)
        assert not AccessibilityStatementPage.can_create_at(about)

    def test_one_per_home_page(self, home_page):
        add_statement(home_page)

        assert not AccessibilityStatementPage.can_create_at(home_page)

    def test_has_no_pages_under_it(self, home_page):
        statement = add_statement(home_page)

        assert not StandardPage.can_create_at(statement)


class TestPlatformPart:
    """What the code says, the same on every site."""

    def test_says_the_site_partially_conforms_to_wcag_2_2_aa(self, client, home_page):
        add_statement(home_page)

        text = section(client, "How well this site works").get_text(" ", strip=True)

        assert (
            "This website partially conforms to the Web Content Accessibility Guidelines (WCAG) "
            "2.2 at level AA." in text
        )

    def test_lists_the_checks_behind_it(self, client, home_page):
        add_statement(home_page)

        checks = section(client, "How well this site works").select("li")

        assert [li.get_text(strip=True) for li in checks] == [
            str(check) for check in accessibility.CHECKS
        ]

    def test_lists_the_platforms_known_problems_and_when_they_were_reviewed(
        self, client, home_page, known_problems
    ):
        add_statement(home_page)

        part = section(client, "What doesn't work yet")

        assert "The map doesn't zoom." in [li.get_text(strip=True) for li in part.select("li")]
        assert "We last reviewed the website itself on 11 November 2026." in part.get_text(
            " ", strip=True
        )

    def test_says_so_when_the_platform_has_no_known_problems(self, client, home_page, monkeypatch):
        monkeypatch.setattr(accessibility, "KNOWN_PROBLEMS", ())
        add_statement(home_page)

        part = section(client, "What doesn't work yet")

        assert "We don't know of any problems in the website itself." in part.get_text(
            " ", strip=True
        )

    def test_with_nothing_listed_doesnt_point_to_a_list(self, client, home_page, monkeypatch):
        # Still "partially": nothing has audited the whole of WCAG 2.2 AA (standard.md).
        monkeypatch.setattr(accessibility, "KNOWN_PROBLEMS", ())
        add_statement(home_page)

        text = section(client, "How well this site works").get_text(" ", strip=True)

        assert "listed below" not in text
        assert "Partially means not every part of the standard has been checked yet." in text

    def test_points_to_the_charitys_list_when_only_it_has_problems(
        self, client, home_page, monkeypatch
    ):
        monkeypatch.setattr(accessibility, "KNOWN_PROBLEMS", ())
        add_statement(home_page, content_problems="<ul><li>Our 2024 report is a PDF.</li></ul>")

        text = section(client, "How well this site works").get_text(" ", strip=True)

        assert "they're listed below." in text


class TestCharityPart:
    """What the charity writes about its own content."""

    def test_shows_the_commitment_under_the_title(self, client, home_page):
        add_statement(home_page, commitment="We want everyone to be able to read about our work.")

        page = BeautifulSoup(client.get("/accessibility/").content, "html.parser")

        assert page.select_one("main h1 + p").get_text(strip=True) == (
            "We want everyone to be able to read about our work."
        )

    def test_lists_the_charitys_own_problems_and_when_it_checked(self, client, home_page):
        add_statement(
            home_page,
            content_problems="<ul><li>Our 2024 report is a PDF.</li></ul>",
            content_checked=datetime.date(2026, 10, 1),
        )

        text = section(client, "What doesn't work yet").get_text(" ", strip=True)

        assert "In what we've published:" in text
        assert "Our 2024 report is a PDF." in text
        assert "We last checked what we've published on 1 October 2026." in text

    def test_leaves_out_what_the_charity_hasnt_written(self, client, home_page):
        add_statement(home_page)

        text = BeautifulSoup(client.get("/accessibility/").content, "html.parser").main.get_text()

        assert "In what we've published" not in text
        assert "We last checked what we've published" not in text


class TestTellUs:
    HEADING = "Tell us about a problem or ask for another format"

    def test_gives_the_general_enquiries_details(self, client, site, home_page):
        settings = SiteSettings.for_site(site)
        settings.phone = "01-4567890"
        settings.contact_email = "hello@brightwell.example"
        settings.save()
        add_statement(home_page)

        part = section(client, self.HEADING)

        assert [(a.get_text(), a["href"]) for a in part.select("a")] == [
            ("01-4567890", "tel:+97714567890"),
            ("hello@brightwell.example", "mailto:hello@brightwell.example"),
        ]

    def test_links_to_the_contact_page_once_it_is_live(
        self, client, site, home_page, privacy_notice
    ):
        contact = ContactPage(title="Contact", slug="contact", to_address="a@brightwell.example")
        home_page.add_child(instance=contact)
        contact.save_revision().publish()
        settings = SiteSettings.for_site(site)
        settings.contact_page = contact
        settings.save()
        add_statement(home_page)

        links = section(client, self.HEADING).select("a")

        assert [(a.get_text(), a["href"]) for a in links] == [("Contact page", "/contact/")]

    def test_doesnt_link_to_a_contact_page_behind_a_login(
        self, client, site, home_page, privacy_notice
    ):
        contact = ContactPage(title="Contact", slug="contact", to_address="a@brightwell.example")
        home_page.add_child(instance=contact)
        contact.save_revision().publish()
        PageViewRestriction.objects.create(page=contact, restriction_type=PageViewRestriction.LOGIN)
        settings = SiteSettings.for_site(site)
        settings.contact_page = contact
        settings.save()
        add_statement(home_page)

        assert section(client, self.HEADING).select("a") == []

    def test_is_shown_with_no_way_to_reach_the_charity(self, client, home_page):
        # A visitor who can't use the site still learns they can ask; the dashboard asks the
        # charity for a way to reach it (test_still_to_write.py).
        add_statement(home_page)

        part = section(client, self.HEADING)

        assert "tell us." in part.get_text(" ", strip=True)
        assert part.select("a") == []

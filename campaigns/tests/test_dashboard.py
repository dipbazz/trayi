import datetime
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from campaigns.models import CampaignPage, Payment, PaymentStatus, Pledge
from campaigns.tests.factories import CampaignIndexPageFactory, CampaignPageFactory
from campaigns.tests.test_qr import make_code
from campaigns.wagtail_hooks import (
    TO_CONFIRM_ROWS,
    PaymentsToConfirmPanel,
    payments_to_confirm,
    waited,
)
from home.wagtail_hooks import StillToWritePanel

TODAY = datetime.date.today()


@pytest.mark.django_db
class TestFundraisingDashboardPanel:
    @pytest.fixture
    def campaigns(self, home_page):
        index = CampaignIndexPageFactory(parent=home_page)
        CampaignPageFactory(
            parent=index,
            title="Flood relief",
            amount_raised=Decimal("10000"),
            end_date=TODAY + datetime.timedelta(days=5),
        )
        CampaignPageFactory(parent=index, title="Clean water", amount_raised=Decimal("2500"))
        CampaignPageFactory(
            parent=index,
            title="Old appeal",
            amount_raised=Decimal("999"),
            start_date=TODAY - datetime.timedelta(days=60),
            end_date=TODAY - datetime.timedelta(days=1),
        )
        CampaignPageFactory(parent=index, title="Draft", amount_raised=Decimal("50"), live=False)

    def test_summarises_open_appeals_on_the_dashboard(self, admin_client, campaigns):
        html = admin_client.get(reverse("wagtailadmin_home")).content.decode()

        assert "Fundraising overview" in html
        assert "Rs 12,500" in html
        assert "2 open appeals" in html

    def test_lists_appeals_closing_within_two_weeks(self, admin_client, campaigns):
        response = admin_client.get(reverse("wagtailadmin_home"))

        html = response.content.decode()
        assert "Closing soon" in html
        assert "Flood relief" in html


def translated(page, locale, **fields):
    """`page`'s published translation into `locale`, with `fields` changed."""
    translation = page.copy_for_translation(locale)
    for name, value in fields.items():
        setattr(translation, name, value)
    translation.save_revision().publish()
    return translation


def closing_soon(html):
    heading = BeautifulSoup(html, "html.parser").find("h3", string="Closing soon")
    return [item.a.get_text(strip=True) for item in heading.find_next("ul").find_all("li")]


@pytest.mark.django_db
class TestTranslatedAppealsCountOnce:
    """An appeal published in both languages is one appeal (#195)."""

    @pytest.fixture
    def appeals(self, home_page, nepali_home_page):
        index = CampaignIndexPageFactory(parent=home_page)
        flood_relief = CampaignPageFactory(
            parent=index,
            title="Flood relief",
            amount_raised=Decimal("10000"),
            end_date=TODAY + datetime.timedelta(days=5),
        )
        CampaignPageFactory(parent=index, title="Clean water", amount_raised=Decimal("2500"))
        nepali_index = translated(index, nepali_home_page.locale)
        translated(flood_relief, nepali_index.locale, title="बाढी राहत")
        return nepali_index

    def test_an_appeal_in_both_languages_counts_once(self, admin_client, appeals):
        html = admin_client.get(reverse("wagtailadmin_home")).content.decode()

        assert "Rs 12,500</strong> raised of Rs 20,000" in html
        assert "2 open appeals" in html

    def test_an_appeal_in_both_languages_closes_soon_once(self, admin_client, appeals):
        html = admin_client.get(reverse("wagtailadmin_home")).content.decode()

        assert closing_soon(html) == ["Flood relief"]

    def test_an_appeal_only_in_the_other_language_still_counts(self, admin_client, appeals):
        CampaignPageFactory(
            parent=appeals,
            title="भूकम्प राहत",
            slug="earthquake-relief",
            amount_raised=Decimal("500"),
            end_date=TODAY + datetime.timedelta(days=3),
        )

        html = admin_client.get(reverse("wagtailadmin_home")).content.decode()

        assert "Rs 13,000</strong> raised of Rs 30,000" in html
        assert "3 open appeals" in html
        assert closing_soon(html) == ["भूकम्प राहत", "Flood relief"]

    def test_an_appeal_unpublished_in_the_main_language_counts_its_other_copy(
        self, admin_client, appeals
    ):
        CampaignPage.objects.get(title="Flood relief").unpublish()

        html = admin_client.get(reverse("wagtailadmin_home")).content.decode()

        assert "Rs 12,500</strong> raised of Rs 20,000" in html
        assert "2 open appeals" in html
        assert closing_soon(html) == ["बाढी राहत"]

    def test_the_main_language_is_counted_when_it_is_nepali(self, admin_client, appeals, settings):
        settings.LANGUAGE_CODE = "ne"

        html = admin_client.get(reverse("wagtailadmin_home")).content.decode()

        assert "2 open appeals" in html
        assert closing_soon(html) == ["बाढी राहत"]


def said_paid(donate_page, code, name, days_ago, amount=2500):
    """A pledge whose supporter said `days_ago` days ago that they paid by scanning `code`."""
    pledge = Pledge.objects.create(
        page=donate_page, amount=amount, currency="NPR", name=name, email="sita@example.com"
    )
    payment = pledge.claim_paid(code, "TXN-8841")
    Payment.objects.filter(pk=payment.pk).update(
        created_at=timezone.now() - datetime.timedelta(days=days_ago, minutes=5)
    )
    return pledge


def dashboard(client):
    return client.get(reverse("wagtailadmin_home")).content.decode()


def to_confirm_panel(html):
    return BeautifulSoup(html, "html.parser").find(id="payments-to-confirm-section")


def rows(html):
    listing = to_confirm_panel(html).select_one("table.listing")
    return [" ".join(row.get_text().split()) for row in listing.select("tbody tr")]


@pytest.mark.django_db
class TestPaymentsToConfirmPanel:
    """The dashboard's list of supporters who say they've paid by QR (#383)."""

    @pytest.fixture
    def code(self):
        return make_code("eSewa")

    @pytest.fixture
    def team(self, client, moderator):
        client.force_login(moderator)
        return client

    def test_lists_the_supporter_who_said_they_paid_longest_ago_first(
        self, team, donate_page, code
    ):
        said_paid(donate_page, code, "Ram Thapa", days_ago=1)
        said_paid(donate_page, code, "Sita Sharma", days_ago=5)
        said_paid(donate_page, code, "Gita Rai", days_ago=2)

        assert rows(dashboard(team)) == [
            "Rs 2,500 · eSewa · Sita Sharma · 5 days ago",
            "Rs 2,500 · eSewa · Gita Rai · 2 days ago",
            "Rs 2,500 · eSewa · Ram Thapa · 1 day ago",
        ]

    def test_lists_only_pledges_to_confirm(self, team, donate_page, code):
        said_paid(donate_page, code, "Sita Sharma", days_ago=1)
        Pledge.objects.create(
            page=donate_page, amount=900, currency="NPR", name="Not paid yet", email="a@example.com"
        )
        marked = said_paid(donate_page, code, "Already marked", days_ago=3)
        marked.payments.get().mark_paid(None, TODAY, 2500, "STMT-1")

        assert rows(dashboard(team)) == ["Rs 2,500 · eSewa · Sita Sharma · 1 day ago"]

    def test_each_row_is_one_link_to_its_pledge(self, team, donate_page, code):
        """Which comes back here once the payment is marked (test_confirming.py)."""
        pledge = said_paid(donate_page, code, "Sita Sharma", days_ago=2)

        links = to_confirm_panel(dashboard(team)).select("tbody a")

        inspect = reverse("pledges:inspect", args=[pledge.pk])
        assert [link["href"] for link in links] == [f"{inspect}?next=%2Fadmin%2F"]

    def test_rows_are_lined_like_the_still_to_write_panel_s(self, team, donate_page, code):
        # Wagtail's dashboard listing draws a line between rows; without one, two rows of
        # "amount · QR · name · when" read as one (#383).
        said_paid(donate_page, code, "Sita Sharma", days_ago=2)
        said_paid(donate_page, code, "Ram Thapa", days_ago=1)

        listing = to_confirm_panel(dashboard(team)).select_one("table.listing.listing--dashboard")

        assert len(listing.select("tbody tr")) == 2

    def test_the_heading_counts_them(self, team, donate_page, code):
        said_paid(donate_page, code, "Sita Sharma", days_ago=2)
        said_paid(donate_page, code, "Ram Thapa", days_ago=1)

        assert "Payments to confirm (2)" in to_confirm_panel(dashboard(team)).get_text()

    def test_lists_ten_then_links_to_all_of_them(self, team, donate_page, code):
        for day in range(TO_CONFIRM_ROWS + 1):
            said_paid(donate_page, code, f"Supporter {day}", days_ago=day + 1)

        html = dashboard(team)

        assert len(rows(html)) == TO_CONFIRM_ROWS
        see_all = to_confirm_panel(html).find("a", string="See all 11")
        listed = team.get(see_all["href"]).content.decode()
        assert all(f"Supporter {day}" in listed for day in range(TO_CONFIRM_ROWS + 1))

    def test_all_of_them_is_the_pledges_list_filtered_to_confirm(self, team, donate_page, code):
        said_paid(donate_page, code, "Sita Sharma", days_ago=1)
        Pledge.objects.create(
            page=donate_page, amount=900, currency="NPR", name="Not paid yet", email="a@example.com"
        )

        listed = team.get(payments_to_confirm().see_all_url).content.decode()

        assert "Sita Sharma" in listed
        assert "Not paid yet" not in listed

    def test_ten_or_fewer_need_no_link_to_all(self, team, donate_page, code):
        said_paid(donate_page, code, "Sita Sharma", days_ago=1)

        assert "See all" not in to_confirm_panel(dashboard(team)).get_text()

    def test_says_nothing_is_waiting_once_a_qr_code_is_set_up(self, team, code):
        panel = to_confirm_panel(dashboard(team))

        assert "Payments to confirm" in panel.get_text()
        assert (
            "Nothing to confirm. When a supporter says they've paid by QR, their payment shows "
            "here." in " ".join(panel.get_text().split())
        )

    def test_isn_t_shown_without_a_qr_code_or_anything_waiting(self, team, site):
        assert to_confirm_panel(dashboard(team)) is None

    def test_a_payment_waiting_is_shown_after_its_qr_code_is_removed(self, team, donate_page, code):
        said_paid(donate_page, code, "Sita Sharma", days_ago=2)
        code.delete()

        assert rows(dashboard(team)) == ["Rs 2,500 · eSewa · Sita Sharma · 2 days ago"]

    def test_a_pledge_with_nothing_left_to_confirm_says_so(self, team, donate_page, code):
        # A QR payment marked not found while an older online try still waits leaves the pledge
        # To confirm with no payment to confirm (#385): its row says so, the dashboard still works.
        pledge = said_paid(donate_page, code, "Sita Sharma", days_ago=2)
        pledge.payments.update(status=PaymentStatus.FAILED)
        pledge.payments.create(method="esewa", amount=2500, currency="NPR")

        assert rows(dashboard(team)) == ["Rs 2,500 · Sita Sharma · Nothing left to confirm"]

    def test_an_editor_doesn_t_see_it(self, client, editor, donate_page, code):
        # Editors can't confirm payments, so the panel would ask them for something they can't do.
        said_paid(donate_page, code, "Sita Sharma", days_ago=2)
        client.force_login(editor)

        assert to_confirm_panel(dashboard(client)) is None

    def test_comes_first_on_the_dashboard(self, team, donate_page, code):
        said_paid(donate_page, code, "Sita Sharma", days_ago=2)

        html = dashboard(team)

        assert html.index('id="payments-to-confirm-section"') < html.index(
            'id="fundraising-section"'
        )
        assert PaymentsToConfirmPanel.order < StillToWritePanel.order

    def test_its_queries_don_t_grow_with_the_payments_waiting(self, donate_page, code):
        def queries():
            with CaptureQueriesContext(connection) as run:
                result = payments_to_confirm()
                [(row.amount, row.paid_by, row.ago, row.url) for row in result.rows]
            return len(run.captured_queries)

        nothing_waiting = queries()
        said_paid(donate_page, code, "First", days_ago=1)
        one = queries()
        for day in range(29):
            said_paid(donate_page, code, f"Supporter {day}", days_ago=day + 2)

        assert nothing_waiting == 2  # the count, and whether a QR code is set up
        assert one == queries() == 3  # the count, the oldest ten, and their payments


@pytest.mark.parametrize(
    ("ago", "said"),
    [
        (datetime.timedelta(minutes=20), "less than an hour ago"),
        (datetime.timedelta(hours=1), "1 hour ago"),
        (datetime.timedelta(hours=23, minutes=59), "23 hours ago"),
        (datetime.timedelta(days=1), "1 day ago"),
        (datetime.timedelta(days=2, hours=23), "2 days ago"),
    ],
)
def test_waited_says_how_long_ago_to_the_hour(ago, said):
    now = timezone.now()

    assert waited(now - ago, now) == said

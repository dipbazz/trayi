"""Confirming a QR payment from the pledge's page (#383): the "Confirm this payment" block at the
top, the way back to the dashboard or the filtered Pledges list, a form with a mistake shown again
with what was typed, and the messages that say what happened.

Logged in as a moderator, who may confirm payments; never a superuser.
"""

import datetime
from urllib.parse import urlencode

import pytest
from bs4 import BeautifulSoup
from django.contrib import messages
from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from campaigns.models import Payment, PaymentStatus, Pledge, StepKind
from campaigns.tests.test_qr import make_code
from campaigns.views import to_confirm_list_url, way_back, when

pytestmark = pytest.mark.django_db

DASHBOARD = "/admin/"


@pytest.fixture
def code():
    return make_code("eSewa")


@pytest.fixture
def pledge(donate_page):
    return Pledge.objects.create(
        page=donate_page, amount=2500, currency="NPR", name="Sita Sharma", email="sita@example.com"
    )


@pytest.fixture
def claimed(pledge, code):
    """A QR payment the supporter gave a transaction ID and a screenshot for."""
    return pledge.claim_paid(code, "TXN-8841", receipt=ContentFile(b"png", name="receipt.png"))


@pytest.fixture
def team(client, moderator):
    client.force_login(moderator)
    return moderator


@pytest.fixture
def ram(django_user_model):
    """Another team member, who got there first."""
    return django_user_model.objects.create_user(
        username="ram", first_name="Ram", last_name="Thapa"
    )


def inspect_url(pledge, came_from=""):
    url = reverse("pledges:inspect", args=[pledge.pk])
    return f"{url}?{urlencode({'next': came_from})}" if came_from else url


def mark_paid_url(payment):
    return reverse("pledges:mark_paid", args=[payment.pledge_id, payment.pk])


def not_found_url(payment):
    return reverse("pledges:not_found", args=[payment.pledge_id, payment.pk])


def receipt_url(payment):
    return reverse("pledges:receipt", args=[payment.pledge_id, payment.pk])


def paid_form(amount="2500", reference="RBB-77", **fields):
    return {"received_on": timezone.localdate(), "amount": amount, "reference": reference, **fields}


def open_page(client, pledge, came_from=""):
    return BeautifulSoup(client.get(inspect_url(pledge, came_from)).content, "html.parser")


def text(element):
    return " ".join(element.get_text(" ", strip=True).split())


def block(page):
    """The "Confirm this payment" panel, or None."""
    return page.find(id="confirm-section")


def said(response):
    """The messages a response leaves, as (level, text)."""
    return [(m.level, m.message) for m in get_messages(response.wsgi_request)]


class TestTheConfirmBlock:
    def test_comes_before_the_contact_details(self, client, team, claimed):
        page = open_page(client, claimed.pledge)

        ids = [s["id"] for s in page.select("section[id$='-section']")]
        assert ids.index("confirm-section") < ids.index("contact-section")

    def test_says_who_paid_what_how_and_when(self, client, team, claimed):
        found = text(block(open_page(client, claimed.pledge)))

        assert (
            f"Sita Sharma says they paid Rs 2,500 by eSewa on {when(claimed.created_at)}" in found
        )
        assert "Check your statement first." in found

    def test_shows_the_transaction_id_and_the_screenshot(self, client, team, claimed):
        found = block(open_page(client, claimed.pledge))

        assert "TXN-8841" in text(found)
        assert found.select_one(f"img[src='{receipt_url(claimed)}']")

    def test_holds_the_only_mark_as_paid_form(self, client, team, claimed):
        page = open_page(client, claimed.pledge)

        forms = page.select(f"form[action='{mark_paid_url(claimed)}']")
        assert len(forms) == 1
        assert forms[0].find_parent(id="confirm-section")

    def test_the_screenshot_isn_t_shown_twice(self, client, team, claimed):
        page = open_page(client, claimed.pledge)

        assert len(page.select(f"img[src='{receipt_url(claimed)}']")) == 1

    def test_without_a_screenshot_says_so(self, client, team, pledge, code):
        payment = pledge.claim_paid(code, "TXN-8841")

        found = block(open_page(client, pledge))

        assert "They didn't send a screenshot, only the transaction ID." in text(found)
        assert not found.select_one(f"img[src='{receipt_url(payment)}']")

    def test_without_a_transaction_id_says_so(self, client, team, pledge, code):
        pledge.claim_paid(code, "", receipt=ContentFile(b"png", name="receipt.png"))

        assert "They didn't give a transaction ID." in text(block(open_page(client, pledge)))

    def test_a_screenshot_deleted_after_30_days_says_so(self, client, team, pledge, code):
        payment = pledge.claim_paid(code, "", receipt=ContentFile(b"png", name="receipt.png"))
        payment.delete_receipt()  # as delete_old_receipts does

        found = text(block(open_page(client, pledge)))

        assert "Their screenshot was deleted after 30 days." in found

    def test_with_only_an_id_after_30_days_it_can_t_say_which(self, client, team, pledge, code):
        """Nothing records whether a screenshot was sent once it's deleted."""
        payment = pledge.claim_paid(code, "TXN-8841")
        Payment.objects.filter(pk=payment.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=31)
        )

        found = text(block(open_page(client, pledge)))

        assert (
            "There's no screenshot: they didn't send one, or it was deleted after 30 days." in found
        )

    def test_a_missing_file_isn_t_linked(self, client, team, claimed):
        claimed.receipt.storage.delete(claimed.receipt.name)

        found = block(open_page(client, claimed.pledge))

        assert not found.select_one(f"img[src='{receipt_url(claimed)}']")
        assert "Their screenshot can't be opened: the file is missing." in text(found)

    def test_the_reference_starts_empty_under_what_they_said(self, client, team, claimed):
        found = block(open_page(client, claimed.pledge))

        reference = found.find("input", attrs={"name": "reference"})
        assert not reference.get("value")
        wrapper = reference.find_parent(attrs={"data-field-wrapper": True})
        assert "They said: TXN-8841" in text(wrapper)
        assert found.find("input", attrs={"name": "amount"})["value"] == "2500"

    def test_not_found_is_a_second_choice_after_the_form(self, client, team, claimed):
        found = block(open_page(client, claimed.pledge))

        assert "Can't find it in your statement?" in text(found)
        assert found.select_one(f"form[action='{not_found_url(claimed)}'] .button-secondary")

    def test_an_editor_sees_none(self, client, editor, claimed):
        client.force_login(editor)

        assert block(open_page(client, claimed.pledge)) is None

    def test_a_payment_marked_not_found_keeps_its_form_in_its_history(self, client, team, claimed):
        claimed.mark_not_found(by=None)

        page = open_page(client, claimed.pledge)

        assert block(page) is None
        form = page.select_one(f"form[action='{mark_paid_url(claimed)}']")
        assert form.find_parent(id="payments-section")
        assert not form.find("input", attrs={"name": "reference"}).get("value")


@pytest.mark.parametrize(
    ("came_from", "kept"),
    [
        (DASHBOARD, True),
        (to_confirm_list_url(), True),
        (f"{to_confirm_list_url()}&p=2", True),
        ("/admin/pledges/", False),  # the whole list: they stay on the pledge
        ("/admin/pledges/?q=Sita", False),  # a search
        ("/admin/pages/", False),
        ("https://evil.example/admin/", False),
        ("//evil.example/admin/", False),
        ("javascript:alert(1)", False),
    ],
)
def test_the_way_back_is_only_this_site_s_dashboard_or_filtered_list(came_from, kept):
    request = RequestFactory().get("/", {"next": came_from})

    assert way_back(request) == (came_from if kept else "")


class TestTheWayBack:
    @pytest.mark.parametrize("came_from", [DASHBOARD, to_confirm_list_url()])
    def test_mark_as_paid_goes_back(self, client, team, claimed, came_from):
        response = client.post(mark_paid_url(claimed), paid_form(next=came_from))

        assert (response.status_code, response.url) == (302, came_from)

    @pytest.mark.parametrize("came_from", [DASHBOARD, to_confirm_list_url()])
    def test_not_found_goes_back(self, client, team, claimed, came_from):
        response = client.post(not_found_url(claimed), {"next": came_from})

        assert (response.status_code, response.url) == (302, came_from)

    @pytest.mark.parametrize("came_from", ["", "/admin/pledges/?q=Sita", "https://evil.example/"])
    def test_from_anywhere_else_both_stay_on_the_pledge(
        self, client, team, pledge, code, came_from
    ):
        first = pledge.claim_paid(code, "TXN-1")
        missing = client.post(not_found_url(first), {"next": came_from})
        second = pledge.claim_paid(code, "TXN-2")
        paid = client.post(mark_paid_url(second), paid_form(next=came_from))

        assert [missing.url, paid.url] == [inspect_url(pledge)] * 2

    @pytest.mark.parametrize("came_from", [DASHBOARD, to_confirm_list_url()])
    def test_the_pledge_page_passes_it_on_to_both_forms(self, client, team, claimed, came_from):
        page = open_page(client, claimed.pledge, came_from)

        for action in (mark_paid_url(claimed), not_found_url(claimed)):
            form = page.select_one(f"form[action='{action}']")
            assert form.find("input", attrs={"name": "next"})["value"] == came_from

    def test_the_pledge_page_drops_another_site(self, client, team, claimed):
        page = open_page(client, claimed.pledge, "https://evil.example/admin/")

        assert not page.find("input", attrs={"name": "next"})

    def test_the_dashboard_s_rows_carry_it(self, client, team, claimed):
        page = BeautifulSoup(client.get(DASHBOARD).content, "html.parser")

        link = page.find(id="payments-to-confirm-section").find("ul").find("a")
        assert link["href"] == inspect_url(claimed.pledge, DASHBOARD)

    def test_the_filtered_list_s_rows_carry_it(self, client, team, claimed):
        page = BeautifulSoup(client.get(to_confirm_list_url()).content, "html.parser")

        # The name and the Inspect button.
        links = {a["href"] for a in page.select("table a") if "/inspect/" in a["href"]}
        assert links == {inspect_url(claimed.pledge, to_confirm_list_url())}

    def test_the_whole_list_s_rows_don_t(self, client, team, claimed):
        page = BeautifulSoup(client.get(reverse("pledges:index")).content, "html.parser")

        links = {a["href"] for a in page.select("table a") if "/inspect/" in a["href"]}
        assert links == {reverse("pledges:inspect", args=[claimed.pledge_id])}


class TestAMistakeInTheForm:
    def post_a_mistake(self, client, claimed):
        return client.post(
            mark_paid_url(claimed),
            {
                "received_on": "2083-08-12",
                "amount": "2,500",
                "reference": "RBB-77",
                "next": DASHBOARD,
            },
        )

    def test_shows_the_page_again_with_what_was_typed(self, client, team, claimed):
        response = self.post_a_mistake(client, claimed)

        assert response.status_code == 422
        found = block(BeautifulSoup(response.content, "html.parser"))
        values = {
            box["name"]: box.get("value") for box in found.select("form input:not([type=hidden])")
        }
        assert values == {"received_on": "2083-08-12", "amount": "2,500", "reference": "RBB-77"}

    def test_says_what_s_wrong_by_its_box(self, client, team, claimed):
        found = block(BeautifulSoup(self.post_a_mistake(client, claimed).content, "html.parser"))

        date = found.find("input", attrs={"name": "received_on"})
        assert "It can't be after today." in text(
            date.find_parent(attrs={"data-field-wrapper": True})
        )

    def test_keeps_the_way_back(self, client, team, claimed):
        found = block(BeautifulSoup(self.post_a_mistake(client, claimed).content, "html.parser"))

        assert found.find("input", attrs={"name": "next"})["value"] == DASHBOARD

    def test_changes_nothing(self, client, team, claimed):
        self.post_a_mistake(client, claimed)

        claimed.refresh_from_db()
        assert claimed.status == PaymentStatus.TO_CONFIRM


class TestWhatItSays:
    def test_marked_paid_names_the_supporter_and_the_amount(self, client, team, claimed):
        response = client.post(mark_paid_url(claimed), paid_form())

        assert said(response) == [(messages.SUCCESS, "Marked Sita Sharma's Rs 2,500 paid.")]

    def test_another_amount_says_the_pledge_now_needs_checking(self, client, team, claimed):
        response = client.post(mark_paid_url(claimed), paid_form(amount="2000"))

        assert said(response) == [
            (
                messages.SUCCESS,
                "Marked Sita Sharma's Rs 2,000 paid. The pledge was for Rs 2,500, so it now says "
                "Needs checking.",
            )
        ]

    def test_marked_not_found_names_the_supporter_and_the_amount(self, client, team, claimed):
        response = client.post(not_found_url(claimed))

        assert said(response) == [(messages.SUCCESS, "Marked Sita Sharma's Rs 2,500 not found.")]

    def test_already_paid_says_who_and_when_as_information(self, client, team, claimed, ram):
        claimed.mark_paid(ram, timezone.localdate(), 2500, "RBB-77")
        at = claimed.steps.get(kind=StepKind.MARKED_PAID).at

        response = client.post(mark_paid_url(claimed), paid_form(next=DASHBOARD))

        assert said(response) == [
            (messages.INFO, f"Ram Thapa already marked Sita Sharma's Rs 2,500 paid on {when(at)}")
        ]
        assert response.url == DASHBOARD

    def test_a_second_tap_says_you(self, client, team, claimed):
        client.post(mark_paid_url(claimed), paid_form(), follow=True)  # its message read
        at = claimed.steps.get(kind=StepKind.MARKED_PAID).at

        response = client.post(mark_paid_url(claimed), paid_form())

        assert said(response) == [
            (messages.INFO, f"You already marked Sita Sharma's Rs 2,500 paid on {when(at)}")
        ]

    def test_not_found_after_it_was_paid_says_so(self, client, team, claimed, ram):
        claimed.mark_paid(ram, timezone.localdate(), 2500, "RBB-77")
        at = claimed.steps.get(kind=StepKind.MARKED_PAID).at

        response = client.post(not_found_url(claimed))

        assert said(response) == [
            (messages.INFO, f"Ram Thapa already marked Sita Sharma's Rs 2,500 paid on {when(at)}")
        ]

    def test_already_not_found_says_who_and_when(self, client, team, claimed, ram):
        claimed.mark_not_found(ram)
        at = claimed.steps.get(kind=StepKind.NOT_FOUND).at

        response = client.post(not_found_url(claimed), {"next": DASHBOARD})

        assert said(response) == [
            (
                messages.INFO,
                f"Ram Thapa already marked Sita Sharma's Rs 2,500 not found on {when(at)}",
            )
        ]
        assert response.url == DASHBOARD

    def test_a_pledge_another_payment_paid_says_how(self, client, team, claimed):
        online = claimed.pledge.payments.create(
            method="esewa", amount=2500, currency="NPR", status=PaymentStatus.PAID, live=True
        )

        response = client.post(mark_paid_url(claimed), paid_form())

        assert said(response) == [
            (
                messages.WARNING,
                f"Sita Sharma's pledge is already paid, by eSewa on {when(online.updated_at)}, so "
                "this payment can't be marked paid too.",
            )
        ]
        claimed.refresh_from_db()
        assert claimed.status == PaymentStatus.TO_CONFIRM

    def test_opened_from_the_dashboard_once_it_s_done_says_so_with_a_link_back(
        self, client, team, claimed, ram
    ):
        claimed.mark_paid(ram, timezone.localdate(), 2500, "RBB-77")
        at = claimed.steps.get(kind=StepKind.MARKED_PAID).at

        page = open_page(client, claimed.pledge, DASHBOARD)

        done = page.select_one(".pledge-done")
        assert text(done) == (
            f"Ram Thapa already marked Sita Sharma's Rs 2,500 paid on {when(at)} "
            "Back to the dashboard"
        )
        assert done.find("a")["href"] == DASHBOARD

    def test_opened_from_the_pledges_list_it_says_nothing_more(self, client, team, claimed, ram):
        claimed.mark_paid(ram, timezone.localdate(), 2500, "RBB-77")

        assert open_page(client, claimed.pledge).select_one(".pledge-done") is None

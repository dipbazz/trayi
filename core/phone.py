import re

import phonenumbers
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.utils.translation import gettext_lazy
from phonenumbers import PhoneNumberFormat, PhoneNumberType

# Countries offered for phone numbers: Nepal, then where most Nepali supporters live or work.
# Add a country with its ISO 3166 code; the calling code comes from phonenumbers. Names stay in
# English everywhere, so the list reads the same in the admin and on supporters' forms.
PHONE_COUNTRIES = (
    ("NP", "Nepal"),
    ("IN", "India"),
    ("GB", "United Kingdom"),
    ("US", "United States"),
    ("AU", "Australia"),
    ("CA", "Canada"),
    ("QA", "Qatar"),
    ("AE", "United Arab Emirates"),
    ("SA", "Saudi Arabia"),
    ("KW", "Kuwait"),
    ("MY", "Malaysia"),
    ("JP", "Japan"),
    ("KR", "South Korea"),
)

# Number types that can receive a text or WhatsApp message. Some countries (the US, Canada,
# India) don't tell mobiles and landlines apart, so those numbers are accepted too.
MESSAGEABLE_TYPES = {PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE}

PHONE_CHARACTERS = re.compile(r"^[\d\s()+.-]+$")

# What the phone box takes as typed. A number is saved in E.164 (at most 16 characters), but
# people type spaces, dashes and brackets, so the box allows more; the form normalises it.
PHONE_BOX_LENGTH = 30


def phone_country_choices():
    choices = []
    for code, name in PHONE_COUNTRIES:
        calling_code = phonenumbers.country_code_for_region(code)
        choices.append((code, f"{name} (+{calling_code})"))
    return choices


def default_phone_country(site_settings):
    """The country a form's phone picker starts on: Site settings' phone country. #274 may later
    take the registration country instead, here alone."""
    return site_settings.phone_country


class PhoneWithCountryMixin:
    """A form's `phone` field with its country picker, the same on every form that asks for a
    number (Donate, Contact), rendered by includes/phone_field.html.

    It adds a `phone_country` field just before `phone`, starting on `phone_country` (pass
    default_phone_country(site_settings)), and makes `phone` a tel box. The form's clean() calls
    normalise_phone_field with the normaliser it needs, once it knows whether to keep the number.
    """

    def __init__(self, *args, phone_country, **kwargs):
        super().__init__(*args, **kwargs)
        country = forms.ChoiceField(
            choices=phone_country_choices, label=gettext_lazy("Country"), initial=phone_country
        )
        fields = {}
        for name, field in self.fields.items():
            if name == "phone":
                fields["phone_country"] = country
            fields[name] = field
        self.fields = fields
        phone = self.fields["phone"]
        phone.max_length = PHONE_BOX_LENGTH
        phone.validators = [MaxLengthValidator(PHONE_BOX_LENGTH)]
        phone.widget.attrs.update(
            {"type": "tel", "autocomplete": "tel-national", "maxlength": str(PHONE_BOX_LENGTH)}
        )

    def normalise_phone_field(self, cleaned_data, normalise):
        """Put the typed number in E.164 with `normalise` (normalise_phone or normalise_mobile),
        or add its error to the phone field."""
        phone = cleaned_data.get("phone", "").strip()
        if phone and cleaned_data.get("phone_country"):
            try:
                cleaned_data["phone"] = normalise(phone, cleaned_data["phone_country"])
            except ValidationError as error:
                self.add_error("phone", error)


def parse_phone(number, region):
    """Return the valid number `number` names, or None.

    A number typed with its own +country code keeps it; otherwise `region` supplies it.
    """
    if not PHONE_CHARACTERS.match(number):
        return None
    try:
        parsed = phonenumbers.parse(number, region)
    except phonenumbers.NumberParseException:
        return None
    return parsed if phonenumbers.is_valid_number(parsed) else None


def normalise_phone(number, region):
    """Return any valid phone number in E.164 (+97714567890), or raise ValidationError."""
    parsed = parse_phone(number, region)
    if parsed is None:
        example = phonenumbers.example_number(region)
        raise ValidationError(
            gettext_lazy("Enter a phone number, like %(example)s."),
            code="invalid_phone",
            params={"example": phonenumbers.format_number(example, PhoneNumberFormat.NATIONAL)},
        )
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def normalise_mobile(number, region):
    """Return a mobile number in E.164 (+9779841234567), or raise ValidationError."""
    parsed = parse_phone(number, region)
    if parsed is None or phonenumbers.number_type(parsed) not in MESSAGEABLE_TYPES:
        example = phonenumbers.example_number_for_type(region, PhoneNumberType.MOBILE)
        raise ValidationError(
            gettext_lazy("Enter a mobile number, like %(example)s."),
            code="invalid_mobile",
            params={"example": phonenumbers.format_number(example, PhoneNumberFormat.NATIONAL)},
        )
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)

import re

import phonenumbers
from django.core.exceptions import ValidationError
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


def phone_country_choices():
    choices = []
    for code, name in PHONE_COUNTRIES:
        calling_code = phonenumbers.country_code_for_region(code)
        choices.append((code, f"{name} (+{calling_code})"))
    return choices


def _parse(number, region):
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
    parsed = _parse(number, region)
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
    parsed = _parse(number, region)
    if parsed is None or phonenumbers.number_type(parsed) not in MESSAGEABLE_TYPES:
        example = phonenumbers.example_number_for_type(region, PhoneNumberType.MOBILE)
        raise ValidationError(
            gettext_lazy("Enter a mobile number, like %(example)s."),
            code="invalid_mobile",
            params={"example": phonenumbers.format_number(example, PhoneNumberFormat.NATIONAL)},
        )
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)

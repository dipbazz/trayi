import re

import phonenumbers
from django import template
from phonenumbers import PhoneNumberFormat

from core.phone import parse_phone

register = template.Library()


@register.filter
def tel_href(number, region):
    """A tel: link for a number as the charity wrote it: {{ site_settings.phone|tel_href:
    site_settings.phone_country }}. A number written the local way gets its country code from
    `region`; one that can't be read keeps only its digits and a leading +."""
    number = (number or "").strip()
    if not number:
        return ""
    parsed = parse_phone(number, region)
    if parsed is not None:
        return "tel:" + phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    plus = "+" if number.startswith("+") else ""
    return "tel:" + plus + re.sub(r"\D", "", number)

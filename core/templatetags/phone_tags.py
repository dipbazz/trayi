import re

import phonenumbers
from django import template
from phonenumbers import Leniency, PhoneNumberFormat, PhoneNumberMatcher

register = template.Library()


@register.filter
def tel_href(number, region):
    """A tel: link for a number as the charity wrote it: {{ site_settings.phone|tel_href:
    site_settings.phone_country }}. A number written the local way gets its country code from
    `region`. Of several numbers the first is linked, and an extension is left to the caller;
    text with none that can be read keeps only its digits and a leading +."""
    number = (number or "").strip()
    if not number:
        return ""
    for match in PhoneNumberMatcher(number, region, leniency=Leniency.VALID):
        return "tel:" + phonenumbers.format_number(match.number, PhoneNumberFormat.E164)
    plus = "+" if number.startswith("+") else ""
    return "tel:" + plus + re.sub(r"\D", "", number)

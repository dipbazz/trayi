import phonenumbers
from django import template
from phonenumbers import Leniency, PhoneNumberFormat, PhoneNumberMatcher

register = template.Library()


@register.filter
def tel_href(number, region):
    """A tel: link for a number as the charity wrote it: {{ site_settings.phone|tel_href:
    site_settings.phone_country }}. A number written the local way gets its country code from
    `region`. Of several numbers the first is linked, and an extension is left to the caller.
    Text with no number that can be read gives "", so the page shows it without a link: a link
    without its country code would fail for a supporter calling from abroad."""
    for match in PhoneNumberMatcher((number or "").strip(), region, leniency=Leniency.VALID):
        return "tel:" + phonenumbers.format_number(match.number, PhoneNumberFormat.E164)
    return ""

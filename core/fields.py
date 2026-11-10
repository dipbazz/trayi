from django.core.validators import URLValidator
from django.db import models

# Only editors see it, and the admin is in English.
PASTE_AN_HTTPS_LINK = "Paste the link that starts with https://"


class HttpsURLField(models.URLField):
    """A link the charity pastes, which visitors open from the site, so https only (#322): an
    http link, or text that isn't a link, gets one message saying what to paste, never Django's
    "Enter a valid URL"."""

    default_validators = [URLValidator(schemes=["https"], message=PASTE_AN_HTTPS_LINK)]

    def formfield(self, **kwargs):
        return super().formfield(**{"error_messages": {"invalid": PASTE_AN_HTTPS_LINK}, **kwargs})

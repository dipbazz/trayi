"""A form copy's one-time ID, the same on every form that saves a copy sent again once."""

import uuid

from django import forms


class CopyIdField(forms.CharField):
    """A copy's one-time ID, cleaned to its text, or None when it's missing or unreadable (a page
    opened before IDs existed): never a reason to turn a send away. Marked data-copy-id, so
    charity.js puts back the copy's ID when the form is reached with Back (the pledge form, every
    form page)."""

    widget = forms.HiddenInput(attrs={"data-copy-id": True})

    def __init__(self, **kwargs):
        super().__init__(required=False, initial=uuid.uuid4, **kwargs)

    def to_python(self, value):
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            return None

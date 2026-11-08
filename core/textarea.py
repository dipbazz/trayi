"""A form's free-text box, the same on every form: a <textarea> with a length limit and a count."""

from django import forms
from django.utils.translation import gettext_lazy


class TextareaField(forms.CharField):
    """Text from a <textarea>, with line breaks counted as one character, as the browser counts
    them against maxlength while the visitor types.

    Browsers send each line break as two characters (CRLF), so a message that fits the box would
    otherwise fail max_length by one character per line.

    With a max_length, charity.js shows "10/1000 characters" below the box (data-char-count), in
    these words; without JavaScript, maxlength alone stops typing at the limit.
    """

    widget = forms.Textarea

    def to_python(self, value):
        return super().to_python(value).replace("\r\n", "\n")

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        if self.max_length is not None and not widget.is_hidden:
            attrs.update(
                {
                    "data-char-count": "",
                    "data-count-text": gettext_lazy("{typed}/{limit} characters"),
                    "data-left-text": gettext_lazy("You have {left} characters left."),
                    "data-full-text": gettext_lazy(
                        "You've reached the limit of {limit} characters."
                    ),
                }
            )
        return attrs

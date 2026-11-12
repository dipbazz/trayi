import json
import logging
import uuid

from django import forms
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.http import HttpResponseRedirect
from django.utils import translation
from django.utils.translation import gettext_lazy
from modelcluster.fields import ParentalKey
from wagtail.admin.mail import send_mail
from wagtail.admin.panels import (
    FieldPanel,
    FieldRowPanel,
    InlinePanel,
    MultiFieldPanel,
)
from wagtail.contrib.forms.forms import BaseForm, FormBuilder
from wagtail.contrib.forms.models import AbstractEmailForm, AbstractFormField
from wagtail.contrib.forms.panels import FormSubmissionsPanel
from wagtail.fields import RichTextField
from wagtail.models import Orderable

from core.honeypot import HoneypotFormMixin
from core.languages import main_language
from core.models import SiteSettings
from core.phone import PhoneWithCountryMixin, default_phone_country, normalise_phone
from core.publishing import FormPageForm, PublishGuardMixin
from core.textarea import TextareaField

logger = logging.getLogger(__name__)


class FormField(AbstractFormField):
    page = ParentalKey("FormPage", on_delete=models.CASCADE, related_name="form_fields")


# Each copy of a form page's form carries a one-time ID in a hidden field (#326), saved in the
# submission's form_data under this name. Wagtail's field names never have a hyphen, so no
# editor's question can take it.
COPY_ID = "copy-id"


class CopyIdField(forms.CharField):
    """A copy's one-time ID, cleaned to its text, or None when it's missing or unreadable (a page
    opened before IDs existed): never a reason to turn a message away. Marked data-copy-id, so
    charity.js puts back the ID that was sent when the form is reached with Back."""

    widget = forms.HiddenInput(attrs={"data-copy-id": True})

    def __init__(self, **kwargs):
        super().__init__(required=False, initial=uuid.uuid4, **kwargs)

    def to_python(self, value):
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            return None


class EmailFormPage(HoneypotFormMixin, PublishGuardMixin, AbstractEmailForm):
    """What every form page does (#167): drop a filled hidden box, email the team with Reply-To
    set to the sender, keep the send when the mail server is down, go on to `?sent` after it,
    answer a send with mistakes with 422, and export what visitors typed as text. Abstract, so
    it has no table of its own.

    A type declares what the base can't: its field model, with a ParentalKey to it and
    related_name="form_fields", and its own form and landing templates, since what the page shows
    around the form is the type's."""

    collects_personal_details = True
    base_form_class = FormPageForm

    class Meta:
        abstract = True

    def serve(self, request, *args, **kwargs):
        if request.method in ("GET", "HEAD") and "sent" in request.GET:
            return self.render_landing_page(request, None, *args, **kwargs)
        response = super().serve(request, *args, **kwargs)
        # Not sent: the form again, with what is wrong with it (422), as on every form.
        if request.method == "POST" and response.status_code == 200:
            response.status_code = 422
        return response

    def render_landing_page(self, request, form_submission=None, *args, **kwargs):
        """After a send, go on to `?sent` (303, so the browser asks for it again with GET): a
        reload then can't send it twice. Opening `?sent`, or the admin's preview, only thanks.
        The address is the one the form was sent to, which works where get_url() gives None."""
        if request.method == "POST":
            return HttpResponseRedirect(f"{request.path}?sent", status=303)
        return super().render_landing_page(request, form_submission, *args, **kwargs)

    def get_submissions_list_view_class(self):
        from contact.views import FormSubmissionsListView  # admin views need the models loaded

        return FormSubmissionsListView

    # A field's label in the email when it isn't the form's, by name. A type sets its own.
    email_labels = {}

    def get_form_class(self):
        """The type's form, with this copy's one-time ID (COPY_ID)."""
        form_class = super().get_form_class()
        return type(form_class.__name__, (form_class,), {COPY_ID: CopyIdField()})

    def process_form_submission(self, form):
        """Save and email only the data fields (get_data_fields), so a field that only helps
        fill in another, like the phone's country, is neither kept nor sent (#321). Wagtail
        saves and emails the form's answers, so the others are dropped from them first.

        A copy already saved with the same answers (sent_before) is neither saved nor emailed
        again (#326). Otherwise its ID is saved with the answers, but neither emailed nor shown
        in the admin's list or export, which list only the data fields: Wagtail's email lists
        the form's fields, so the ID's field is dropped from them."""
        copy = form.cleaned_data.get(COPY_ID)
        names = {name for name, label in self.get_data_fields()}
        for name in form.cleaned_data.keys() - names:
            del form.cleaned_data[name]
        earlier = self.sent_before(copy, form.cleaned_data)
        if earlier is not None:
            return earlier
        if copy is not None:
            form.cleaned_data[COPY_ID] = copy
        form.fields.pop(COPY_ID, None)
        return super().process_form_submission(form)

    def sent_before(self, copy, answers):
        """This page's submission from the copy `copy` with these answers, if there is one. The
        answers count too: a copy changed after Back and sent again is what the sender meant, so
        it's saved. One worker serves the site, on SQLite, so two sends of a copy never race."""
        if copy is None:
            return None
        answers = json.loads(json.dumps(answers, cls=DjangoJSONEncoder))
        sent = self.get_submission_class().objects.filter(
            page=self, **{f"form_data__{COPY_ID}": copy}
        )
        for submission in sent:
            if {k: v for k, v in submission.form_data.items() if k != COPY_ID} == answers:
                return submission
        return None

    def render_email(self, form):
        """Wagtail's email, with each field under its `email_labels` label (the Contact page's
        number reads "Phone", not "Number"), in the site's main language, which the team reads,
        whichever one the sender wrote in."""
        for name, label in self.email_labels.items():
            if name in form.fields:
                form[name].label = label
        with translation.override(main_language()):
            return super().render_email(form)

    def reply_to_address(self, form):
        """The sender's address for Reply-To, or None: the first email field they filled in. The
        form already holds its fields, so this reads no questions again."""
        email_fields = [
            name for name, field in form.fields.items() if isinstance(field, forms.EmailField)
        ]
        filled = [form.cleaned_data[name] for name in email_fields if form.cleaned_data.get(name)]
        return filled[0] if filled else None

    def send_mail(self, form):
        """Email the team, with Reply-To set to the sender so staff can answer directly."""
        reply_to = self.reply_to_address(form)
        try:
            send_mail(
                self.subject,
                self.render_email(form),
                [address.strip() for address in self.to_address.split(",")],
                self.from_address,
                reply_to=[reply_to] if reply_to else None,
            )
        except OSError:
            # The submission is already saved and listed in the admin, so a mail outage
            # shouldn't show the sender an error page and make them submit again.
            logger.exception("Could not email the submission for form page %s", self.pk)


class FormPage(EmailFormPage):
    """A form editors build themselves, e.g. volunteer sign-up or general enquiries."""

    intro = RichTextField(blank=True)
    thank_you_text = RichTextField(blank=True)

    content_panels = AbstractEmailForm.content_panels + [
        FormSubmissionsPanel(),
        FieldPanel("intro"),
        InlinePanel("form_fields", label="Form fields"),
        FieldPanel("thank_you_text"),
        MultiFieldPanel(
            [
                FieldRowPanel([FieldPanel("from_address"), FieldPanel("to_address")]),
                FieldPanel("subject"),
            ],
            heading="Email notification",
        ),
    ]

    parent_page_types = ["home.HomePage", "home.StandardPage"]
    subpage_types = []


# Asked once, on the Contact page, when a sender gives neither (#167): first in the error summary,
# under the Email box, and named by the Phone group.
CONTACT_NEEDED = gettext_lazy("Give us an email or phone number so we can reply.")

# What every Contact page asks first, saved under these names in every language, with the
# submissions list's labels. The country only helps read the number, so it's never saved.
CORE_FIELDS = {
    "name": gettext_lazy("Your name"),
    "email": gettext_lazy("Email"),
    "phone": gettext_lazy("Phone"),
    "message": gettext_lazy("Your message"),
}
RESERVED_NAMES = {*CORE_FIELDS, "phone_country", "submit_time"}


class ContactForm(PhoneWithCountryMixin, BaseForm):
    """The Contact page's fixed core, which the editor's own questions follow (the form builder
    subclasses it): Your name, Email, Phone with its country, Your message. Email or phone is
    needed, so the charity can reply."""

    # Adds "(optional)" to the labels of fields marked show_optional.
    template_name_label = "campaigns/forms/label.html"

    name = forms.CharField(
        label=CORE_FIELDS["name"],
        max_length=255,
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
        error_messages={"required": gettext_lazy("Enter your name.")},
    )
    email = forms.EmailField(
        label=CORE_FIELDS["email"],
        required=False,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    # Under its "Phone (optional)" legend, as on the Donate form.
    phone = forms.CharField(label=gettext_lazy("Number"), required=False)
    # About a page: room for a real enquiry, short enough for the team to read every one.
    message = TextareaField(
        label=CORE_FIELDS["message"],
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 6}),
        error_messages={"required": gettext_lazy("Enter your message.")},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].show_optional = True

    def clean(self):
        cleaned_data = super().clean()
        self.normalise_phone_field(cleaned_data, normalise_phone)
        unreadable = "email" in self.errors or "phone" in self.errors
        if not unreadable and not cleaned_data.get("email") and not cleaned_data.get("phone"):
            self.add_error(None, CONTACT_NEEDED)
            self.add_error("email", CONTACT_NEEDED)
        return cleaned_data

    @property
    def phone_describedby(self):
        """The Email box's error id while it says email or phone is needed, for the Phone group."""
        if CONTACT_NEEDED in self.non_field_errors():
            return f"{self['email'].auto_id}_error"
        return ""

    def extra_fields(self):
        """The editor's own questions, after the core."""
        return [field for field in self.visible_fields() if field.name not in RESERVED_NAMES]


class ContactFormBuilder(FormBuilder):
    def get_form_class(self):
        return type("ContactPageForm", (ContactForm,), self.formfields)


class ContactPageForm(FormPageForm):
    """The admin form: an extra question can't take a core field's name, or its answers would
    overwrite the core field's (#167). Wagtail's own check compares the extra questions only."""

    def clean(self):
        cleaned_data = super().clean()
        formset = self.formsets.get("form_fields")
        for form in formset.forms if formset else ():
            if form.cleaned_data.get("DELETE") or not form.cleaned_data.get("label"):
                continue
            clean_name = form.instance.clean_name or form.instance.get_field_clean_name()
            if clean_name in RESERVED_NAMES:
                form.add_error(
                    "label",
                    f"“{form.cleaned_data['label']}” is already a question on every Contact "
                    "page. Give this question another name.",
                )
        return cleaned_data


class ContactFormField(AbstractFormField):
    page = ParentalKey("ContactPage", on_delete=models.CASCADE, related_name="form_fields")


# Editors see it, in the admin's English.
TEAM_CONTACT_NEEDED = "Give this team an email or a phone number, or both."


class ContactTeam(Orderable):
    """A team listed under Other contacts on the Contact page, such as Finance (#322). It's part
    of the page, so Translate copies it with the page and each language keeps its own."""

    page = ParentalKey("ContactPage", on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=100, help_text="For example, Finance or Volunteering.")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    panels = [FieldPanel("name"), FieldRowPanel([FieldPanel("email"), FieldPanel("phone")])]

    class Meta(Orderable.Meta):
        verbose_name = "team"

    def clean_fields(self, exclude=None):
        """Email or phone, checked here rather than in clean() because only this sees which
        fields the form already rejected: a mistyped email then gets Django's message alone,
        not also this one telling the editor to add the email they typed."""
        super().clean_fields(exclude=exclude)
        if {"email", "phone"} & set(exclude or ()):
            return
        if not self.email and not self.phone:
            raise ValidationError({"email": TEAM_CONTACT_NEEDED})


class ContactPage(EmailFormPage):
    """The standard's Contact page (#167): the intro, General enquiries from Site settings, and
    a message form with a fixed core, then the editor's own questions. One per home page, so
    each language has one."""

    intro = RichTextField(blank=True)
    thank_you_text = RichTextField(
        blank=True,
        help_text="Shown after a message is sent. Leave it blank for “We'll reply by email or "
        "phone, using the details you gave.”",
    )

    base_form_class = ContactPageForm
    form_builder = ContactFormBuilder

    content_panels = AbstractEmailForm.content_panels + [
        FormSubmissionsPanel(),
        FieldPanel("intro"),
        InlinePanel(
            "teams",
            heading="Other contacts",
            label="Team",
            help_text="Listed after General enquiries, which come from Site settings. Add a team "
            "only if people can reach it directly.",
        ),
        InlinePanel(
            "form_fields",
            label="Extra questions",
            help_text="Asked after Your name, Email, Phone and Your message, which every "
            "Contact page asks.",
        ),
        FieldPanel("thank_you_text"),
        MultiFieldPanel(
            [
                FieldRowPanel([FieldPanel("from_address"), FieldPanel("to_address")]),
                FieldPanel("subject"),
            ],
            heading="Email notification",
        ),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = []
    max_count_per_parent = 1
    email_labels = CORE_FIELDS

    def serve(self, request, *args, **kwargs):
        # The request's Site settings, which the page reads anyway, so the form costs no query.
        self.site_settings = SiteSettings.for_request(request)
        return super().serve(request, *args, **kwargs)

    def get_form_parameters(self):
        site_settings = getattr(self, "site_settings", None)
        if site_settings is None:  # a form made outside a request
            site_settings = SiteSettings.for_site(self.get_site())
        phone_country = default_phone_country(site_settings)
        return {**super().get_form_parameters(), "phone_country": phone_country}

    def get_data_fields(self):
        submit_time, *extras = super().get_data_fields()
        return [submit_time, *CORE_FIELDS.items(), *extras]

    def reply_to_address(self, form):
        return form.cleaned_data.get("email") or None

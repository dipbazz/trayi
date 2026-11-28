import datetime
import re
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.decorators import method_decorator
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from wagtail.admin.ui.tables import Column
from wagtail.admin.views.generic import DeleteView, EditView, IndexView, InspectView
from wagtail.admin.views.generic.history import HistoryView
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.log_actions import log
from wagtail.snippets.views.snippets import IndexView as SnippetIndexView
from wagtail.snippets.views.snippets import SnippetViewSet

from campaigns import sharing
from campaigns.forms import MarkPaidForm
from campaigns.models import (
    ASK_AGAIN_AFTER,
    RECEIPTS_KEPT_FOR,
    Payment,
    PaymentStatus,
    Pledge,
    QRCode,
    StepKind,
)
from core.exports import VisitorTextExportMixin
from core.images import UPLOAD_CONTENT_TYPES
from core.number_fields import number_formfield


class PledgeIndexView(VisitorTextExportMixin, IndexView):
    def get_base_queryset(self):
        # The export's "Paid with" reads each pledge's payments: fetched together, not one by one.
        return super().get_base_queryset().prefetch_related("payments")

    def get_inspect_url(self, instance):
        """Filtered To confirm, the list is a place to come back to once a payment is marked
        (#383), so its pledges' links say so. Built from the list's own address, not this
        request's: filtering reloads only the results, from another address."""
        url = super().get_inspect_url(instance)
        here = f"{reverse('pledges:index')}?{self.request.GET.urlencode()}"
        return opened_from(url, here) if url and is_way_back(here) else url

    def search_queryset(self, queryset):
        """Names, emails and phone numbers as typed, a pledge number with or without its space
        ("482 913" as it's shown and read out, "482913" as it's written in a payment's remarks),
        and anything on a line of a provider's or bank's statement: a payment's reference (with
        or without its hyphens), the provider's ID, or a transaction ID."""
        found = super().search_queryset(queryset)
        if not self.is_searching:
            return found
        typed = self.search_query.strip()
        digits = re.sub(r"\s", "", typed)
        if re.fullmatch(r"\d{6}", digits):
            found = found | queryset.filter(number=digits)
        payments = (
            Q(provider_id=typed)
            | Q(provider_reference__iexact=typed)
            | Q(supporters_reference__iexact=typed)
        )
        if re.fullmatch(r"[0-9a-fA-F]{32}", typed.replace("-", "")):
            payments |= Q(reference=uuid.UUID(typed.replace("-", "")))
        paid = Payment.objects.filter(payments).values("pledge_id")
        return found | queryset.filter(pk__in=paid)


class PledgeEditView(EditView):
    """Keeps the amount and currency once someone has started paying the pledge: the payment was
    for them, so a changed one still marked paid would disagree with the provider's statement.
    The rest (a mistyped email, say) can still be put right. A disabled field ignores what's
    posted for it."""

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object.payments.exists():
            for name in ("amount", "currency"):
                field = form.fields[name]
                field.disabled = True
                field.help_text = "Can't be changed: someone has started paying this pledge."
        return form


class PledgeDeleteView(DeleteView):
    """Refuses a pledge paid with real money: its payment is the site's only record of the gift
    (provider, transaction ID and time). Unpaid pledges and ones paid in a provider's test system
    can still be deleted, to clear out testing. Wagtail checks permission before get() and post().
    """

    def get(self, request, *args, **kwargs):
        return self.refuse() or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.refuse() or super().post(request, *args, **kwargs)

    def refuse(self):
        if not self.object.received_money():
            return None
        messages.error(
            self.request,
            "This pledge was paid with real money, so it can't be deleted: its payment is the "
            "site's only record of the gift.",
        )
        return redirect("pledges:inspect", self.object.pk)


CONFIRM_PERMISSION = "campaigns.confirm_payment"
STOP_SHOWING_PERMISSION = "campaigns.stop_showing_gift"


def when(moment):
    """A time as the pledge's page shows it, in the site's time zone: "14 Oct 2026, 3:38 p.m."."""
    return date_format(timezone.localtime(moment), "j M Y, g:i a")


def ended(sentence):
    """`sentence` with its full stop, unless it ends with one already: a time ending "p.m."."""
    return sentence if sentence.endswith(".") else f"{sentence}."


def time_zone_name():
    """The site's time zone, named once on the pledge's page: "Asia/Kathmandu time (UTC+5:45)"."""
    offset = timezone.localtime().utcoffset()
    sign = "-" if offset < datetime.timedelta(0) else "+"
    hours, seconds = divmod(abs(int(offset.total_seconds())), 3600)
    return f"{timezone.get_current_timezone_name()} time (UTC{sign}{hours}:{seconds // 60:02d})"


def paid_how(payment):
    """The provider or QR code a payment was made with."""
    return payment.qr_name or payment.get_method_display()


def to_confirm_list_url():
    """The Pledges list filtered To confirm: the dashboard panel's "See all" (#383). It reads the
    pledge's status, as the panel does, so its count and the list agree."""
    return f"{reverse('pledges:index')}?{urlencode({'payment_status': PaymentStatus.TO_CONFIRM})}"


def is_way_back(url):
    """Whether `url` is one of the two places Mark as paid and Not found go back to (#383): the
    dashboard, or the Pledges list filtered To confirm (with any page or search of it). Only an
    address on this site with no host: never another site, and no other admin page."""
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return False
    if parts.path == reverse("wagtailadmin_home"):
        return not parts.query
    shown = parse_qs(parts.query).get("payment_status")
    return parts.path == reverse("pledges:index") and shown == [PaymentStatus.TO_CONFIRM]


def way_back(request):
    """Where the pledge's page was opened from, sent as `next`, if it's a place to go back to
    once a payment is marked (is_way_back); "" otherwise, to stay on the pledge's page. Read the
    same way by the page and by both forms, which pass it on, also after a mistake."""
    url = request.POST.get("next") or request.GET.get("next") or ""
    safe = url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    return url if safe and is_way_back(url) else ""


def opened_from(inspect_url, came_from):
    """A pledge's page that knows where it was opened from, to go back there."""
    return f"{inspect_url}?{urlencode({'next': came_from})}"


def back_label(came_from):
    """The link back to where a pledge was opened from (way_back())."""
    if urlsplit(came_from).path == reverse("wagtailadmin_home"):
        return "Back to the dashboard"
    return "Back to payments to confirm"


def someone(user, by):
    """Who did a step, as a sentence starts: "You" for the person reading."""
    if by is None:
        return "Someone"
    if by == user:
        return "You"
    return by.get_full_name() or by.get_username()


def done_already(user, payment):
    """Why `payment` can't be marked paid or not found now, as (message level, sentence), or None
    when it still can (#383). Someone marked it already (information: it's done), or another
    payment paid its pledge (a warning: the supporter may have paid twice). Reads its steps, and
    its pledge's payments, as fetched."""
    pledge = payment.pledge

    def marked(kind, word):
        step = next((s for s in reversed(payment.steps.all()) if s.kind == kind), None)
        by = someone(user, step.by if step else None)
        on = f" on {when(step.at)}" if step else ""
        return ended(f"{by} already marked {pledge.name}'s {payment.display_amount()} {word}{on}")

    if payment.status == PaymentStatus.PAID:
        return messages.INFO, marked(StepKind.MARKED_PAID, "paid")
    other = next(
        (p for p in pledge.payments.all() if p.status == PaymentStatus.PAID and p != payment), None
    )
    if other:
        return messages.WARNING, (
            f"{pledge.name}'s pledge is already paid, by {paid_how(other)} on "
            f"{when(other.updated_at)}, so this payment can't be marked paid too."
        )
    if payment.status == PaymentStatus.FAILED:
        return messages.INFO, marked(StepKind.NOT_FOUND, "not found")
    return None


def has_screenshot(payment):
    """Whether the supporter's screenshot can be shown: sent, not deleted, and its file there."""
    return bool(payment.receipt) and payment.receipt.storage.exists(payment.receipt.name)


def missing_evidence(payment):
    """A line for each thing the supporter didn't send, or that's gone, in its place in the
    "Confirm this payment" block (#383). A deleted screenshot leaves nothing behind, and a claim
    needs a transaction ID or a screenshot, so with no ID it was deleted; with one, after the 30
    days it may have been, nothing says whether there was one."""
    lines = []
    if not payment.supporters_reference:
        lines.append("They didn't give a transaction ID.")
    if payment.receipt:
        if not has_screenshot(payment):
            lines.append("Their screenshot can't be opened: the file is missing.")
    elif not payment.supporters_reference:
        lines.append("Their screenshot was deleted after 30 days.")
    elif payment.created_at < timezone.now() - RECEIPTS_KEPT_FOR:
        lines.append(
            "There's no screenshot: they didn't send one, or it was deleted after 30 days."
        )
    else:
        lines.append("They didn't send a screenshot, only the transaction ID.")
    return lines


def payment_reason(pledge, payments):
    """The sentence after the pledge's payment status (Pledge.payment_display()) at the top of
    its page: how it was paid, or why it isn't. `payments` are its payments, newest first."""
    if reason := pledge.needs_checking():
        return reason
    if paid := pledge.paid_payment():
        made = f"with {paid_how(paid)} on {when(pledge.paid_at or paid.updated_at)}"
        if paid.provider_reference:
            made += f", transaction {paid.provider_reference}"
        if not paid.live:
            made += f". Made in {paid.get_method_display()}'s test system: no money moved."
        return made
    if claimed := next((p for p in payments if p.status == PaymentStatus.TO_CONFIRM), None):
        sent = f"The supporter says they paid by {paid_how(claimed)}"
        if claimed.supporters_reference:
            sent += f", transaction {claimed.supporters_reference}"
        if claimed.receipt:
            sent += ", and sent a screenshot of the receipt"
        return f"{sent}. Find it in your statement, then mark it paid or not found."
    if not payments:
        return "Not paid online yet."
    latest = payments[0]
    if latest.status == PaymentStatus.WAITING:
        return f"Started with {paid_how(latest)} on {when(latest.created_at)}, not confirmed yet."
    if latest.team_confirms:
        return f"Your team couldn't find the payment by {paid_how(latest)} in its statement."
    if not latest.reached_provider():
        return f"The payment couldn't start at {paid_how(latest)}, so no money was taken."
    return latest.word_sentence() or f"{paid_how(latest)} didn't confirm the payment."


class PledgeInspectView(InspectView):
    """The pledge as the team acts on it: who, how much and whether it's paid; the contact
    details; the message and consents; then its payments with what happened to each. A payment
    the team confirms (a QR payment) is marked paid or not found here, by people who may confirm
    payments; one a provider answers for can be checked with the provider."""

    template_name = "campaigns/admin/pledge_inspect.html"

    def get_page_subtitle(self):
        return self.object.name  # the amount and how often lead the page

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetched once and shared, so the answer, the payments and their steps make no more
        # queries however many there are.
        pledge = (
            Pledge.objects.select_related("page")
            .prefetch_related(Prefetch("payments", Payment.objects.prefetch_related("steps__by")))
            .get(pk=self.object.pk)
        )
        payments = list(pledge.payments.all())
        paid = pledge.paid_payment()
        word = pledge.payment_display()
        shown = pledge.page and sharing.gift_view(pledge) != sharing.HIDDEN
        can_confirm = self.request.user.has_perm(CONFIRM_PERMISSION)
        next_url = way_back(self.request)
        context.update(
            self.confirming(pledge, payments, next_url) if can_confirm else {},
            next_url=next_url,
        )
        context.update(
            # Their page for friends (#100), while it's up, for the team to see what it shows.
            gift_url=sharing.gift_url(pledge, self.request) if shown else "",
            can_stop_showing=self.request.user.has_perm(STOP_SHOWING_PERMISSION),
            pledge=pledge,
            payments=payments,
            # The paid one is open, or else the latest; every other one is folded.
            open_payment=paid or (payments[0] if payments else None),
            payment_word=word,
            # Filled in for paid, so it stands out from the states that need something done.
            payment_word_class="w-status--primary" if word.startswith("Paid") else "",
            payment_reason=payment_reason(pledge, payments),
            time_zone=time_zone_name(),
            can_confirm=can_confirm,
        )
        return context

    def confirming(self, pledge, payments, next_url):
        """What someone who may confirm payments sees (#383): a Mark as paid form for each payment
        the team confirms that isn't paid (the one posted with a mistake, if it was, as typed); the
        "Confirm this payment" block for the payment To confirm; and, opened from the dashboard or
        the filtered list with nothing left to confirm, what happened instead."""
        posted = self.kwargs.get("mark_paid_form")
        for payment in payments:
            if payment.team_confirms and payment.status != PaymentStatus.PAID:
                payment.mark_paid_form = (
                    posted
                    if posted and posted.payment.pk == payment.pk
                    else MarkPaidForm(pledge=pledge, payment=payment)
                )
        claim = next(
            (p for p in payments if p.team_confirms and p.status == PaymentStatus.TO_CONFIRM),
            None,
        )
        if claim:
            return {
                "confirm": {
                    "payment": claim,
                    "said": ended(
                        f"{pledge.name} says they paid {claim.display_amount()} by "
                        f"{paid_how(claim)} on {when(claim.created_at)}"
                    ),
                    "screenshot": has_screenshot(claim),
                    "missing": missing_evidence(claim),
                }
            }
        latest = next((p for p in payments if p.team_confirms), None)
        why = next_url and latest and done_already(self.request.user, latest)
        return {"done": why[1], "back_label": back_label(next_url)} if why else {}

    def post(self, request, *args, **kwargs):
        """Only Mark as paid's form with a mistake (mark_paid_view) comes here: the pledge's page
        again, with what was typed and each mistake by its box (#296), and the way back. Anything
        else posted to the pledge's page is refused."""
        if "mark_paid_form" not in self.kwargs:
            return self.http_method_not_allowed(request, *args, **kwargs)
        response = self.get(request, *args, **kwargs)
        response.status_code = 422
        return response


class PledgeHistoryView(HistoryView):
    """A pledge's history, for anyone who can read pledges, not only those who can change them:
    the team acts on pledges (Stop showing on the website, #100) without editing them."""

    any_permission_required = ["view", "add", "change", "delete"]


class PledgeViewSet(ModelViewSet):
    """Pledges from the Donate page: listed, filtered, read and exported.

    Pledges come from the site, so the team never adds or edits them, and only a superuser can
    delete one (0006_pledge_permissions gives the groups view permission only): a deleted
    pledge loses the record of a donation. Not even a superuser can delete one paid with real
    money (PledgeDeleteView), or change the amount of one someone has started paying
    (PledgeEditView).
    """

    model = Pledge
    name = "pledges"
    icon = "doc-full"
    add_to_admin_menu = True
    menu_order = 250
    inspect_view_enabled = True
    copy_view_enabled = False
    index_view_class = PledgeIndexView
    edit_view_class = PledgeEditView
    delete_view_class = PledgeDeleteView
    inspect_view_class = PledgeInspectView
    history_view_class = PledgeHistoryView

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path(
                "<int:pk>/payments/<int:payment_pk>/mark-paid/",
                self.mark_paid_view,
                name="mark_paid",
            ),
            path(
                "<int:pk>/payments/<int:payment_pk>/not-found/",
                self.not_found_view,
                name="not_found",
            ),
            path(
                "<int:pk>/payments/<int:payment_pk>/receipt/",
                self.receipt_view,
                name="receipt",
            ),
            path(
                "<int:pk>/payments/<int:payment_pk>/check/",
                self.check_view,
                name="check",
            ),
            path("<int:pk>/stop-showing/", self.stop_showing_view, name="stop_showing"),
            path("<int:pk>/show-again/", self.show_again_view, name="show_again"),
        ]

    @staticmethod
    def gift_to_show_or_not(request, pk):
        """The pledge, if this person may take its gift's page down or put it back (a 403
        otherwise): editors and moderators."""
        if not request.user.has_perm(STOP_SHOWING_PERMISSION):
            raise PermissionDenied
        return get_object_or_404(Pledge, pk=pk)

    def stop_showing_view(self, request, pk):
        """Stop showing on the website (#100): takes the gift's page for friends down at once,
        say for a made-up name, after asking first. It sticks: the supporter's box is replaced by
        a note to call, and only Show again puts it back. Logged in the pledge's history."""
        pledge = self.gift_to_show_or_not(request, pk)
        if request.method == "POST":
            # Logged only if it changed: sent twice, or from a tab left open, it's one entry.
            if Pledge.objects.filter(pk=pk, hidden_by_team=False).update(hidden_by_team=True):
                log(instance=pledge, action="campaigns.stop_showing", user=request.user)
            messages.success(request, f"{pledge.name}'s gift isn't shown on the website now.")
            return redirect("pledges:inspect", pk)
        return TemplateResponse(
            request,
            "campaigns/admin/stop_showing.html",
            {
                "pledge": pledge,
                "page_title": "Stop showing on the website",
                "page_subtitle": pledge.name,
                "header_icon": "doc-full",
            },
        )

    @method_decorator(require_POST)
    def show_again_view(self, request, pk):
        """Show again: undoes Stop showing on the website. The page is up again if the supporter
        still agrees to it. Logged in the pledge's history."""
        pledge = self.gift_to_show_or_not(request, pk)
        if Pledge.objects.filter(pk=pk, hidden_by_team=True).update(hidden_by_team=False):
            log(instance=pledge, action="campaigns.show_again", user=request.user)
        messages.success(request, f"{pledge.name}'s gift can be shown on the website again.")
        return redirect("pledges:inspect", pk)

    @method_decorator(require_POST)
    def check_view(self, request, pk, payment_pk):
        """Check with <provider> now: asks the provider about the payment as the pay page does,
        for anyone who can read pledges, and adds the answer to its steps with their name. Not
        again within ASK_AGAIN_AFTER: each ask can wait for the provider."""
        if not request.user.has_perm("campaigns.view_pledge"):
            raise PermissionDenied
        payment = get_object_or_404(Payment, pk=payment_pk, pledge_id=pk)
        name = payment.get_method_display()
        if not payment.can_be_checked():
            messages.error(request, f"This payment can't be checked with {name}.")
        elif payment.asked_recently():
            messages.warning(
                request,
                f"{name} was asked less than {ASK_AGAIN_AFTER.seconds} seconds ago. Wait a "
                "moment, then check again.",
            )
        elif outcome := payment.ask(by=request.user):
            said = payment.word_sentence()
            messages.success(request, said or f"{name} says it's {outcome.status}.")
        else:
            messages.error(
                request,
                f"{payment.steps.last().sentence()} Try again in a few minutes.",
            )
        return redirect(reverse("pledges:inspect", args=[pk]))

    @staticmethod
    def confirmable_payment(request, pk, payment_pk):
        """The payment, if this person may confirm payments (a 403 otherwise). Only payments the
        team confirms are ever changed here: a provider's are never marked by hand."""
        if not request.user.has_perm(CONFIRM_PERMISSION):
            raise PermissionDenied
        return get_object_or_404(
            Payment.objects.select_related("pledge"), pk=payment_pk, pledge_id=pk
        )

    @staticmethod
    def go_back(request, pk):
        """To the dashboard or the filtered list it was opened from, else the pledge's page."""
        return redirect(way_back(request) or reverse("pledges:inspect", args=[pk]))

    @staticmethod
    def say_why_not(request, payment, otherwise):
        """After a refusal, what happened instead, read afresh (done_already()); `otherwise` if
        nothing explains it."""
        payment = (
            Payment.objects.select_related("pledge")
            .prefetch_related("steps__by", "pledge__payments")
            .get(pk=payment.pk)
        )
        if why := done_already(request.user, payment):
            messages.add_message(request, *why)
        else:
            messages.error(request, otherwise)

    @method_decorator(require_POST)
    def mark_paid_view(self, request, pk, payment_pk):
        """Mark as paid: the payment and its pledge paid, then back where the team came from,
        saying whose and how much (#383). The amount received may differ from the pledge's,
        which then needs checking: said now, as the dashboard doesn't list it."""
        payment = self.confirmable_payment(request, pk, payment_pk)
        pledge = payment.pledge
        form = MarkPaidForm(request.POST, pledge=pledge, payment=payment)
        if not form.is_valid():
            messages.error(request, "Not marked paid: put right what's marked below.")
            return self.inspect_view(request, pk=pk, mark_paid_form=form)
        if payment.mark_paid(
            request.user,
            form.cleaned_data["received_on"],
            form.cleaned_data["amount"],
            form.cleaned_data["reference"],
        ):
            sentence = f"Marked {pledge.name}'s {payment.display_amount()} paid."
            if (payment.amount, payment.currency) != (pledge.amount, pledge.currency):
                sentence += (
                    f" The pledge was for {pledge.display_amount()}, so it now says Needs checking."
                )
            messages.success(request, sentence)
        else:
            self.say_why_not(request, payment, "This payment can't be marked paid.")
        return self.go_back(request, pk)

    @method_decorator(require_POST)
    def not_found_view(self, request, pk, payment_pk):
        payment = self.confirmable_payment(request, pk, payment_pk)
        if payment.mark_not_found(request.user):
            messages.success(
                request, f"Marked {payment.pledge.name}'s {payment.display_amount()} not found."
            )
        else:
            self.say_why_not(request, payment, "This payment can't be marked not found.")
        return self.go_back(request, pk)

    def receipt_view(self, request, pk, payment_pk):
        """The supporter's screenshot of their receipt, for people who may confirm payments
        only: nothing else serves it. Never cached, so it's gone from the browser too once it's
        deleted."""
        payment = self.confirmable_payment(request, pk, payment_pk)
        if not payment.receipt:
            raise Http404
        try:
            file = payment.receipt.open("rb")
        except FileNotFoundError as missing:
            raise Http404 from missing
        extension = payment.receipt.name.rpartition(".")[2]
        response = FileResponse(file, content_type=UPLOAD_CONTENT_TYPES[extension])
        add_never_cache_headers(response)
        return response

    def formfield_for_dbfield(self, db_field, **kwargs):
        """The amount is a text box with the number keypad, as on a page's form (#97)."""
        return number_formfield(db_field, **kwargs)

    # Wagtail needs these for its add and edit views, which only a superuser can open.
    form_fields = [
        "appeal",
        "amount",
        "currency",
        "frequency",
        "name",
        "email",
        "phone",
        "address",
        "postcode",
        "message",
        "email_updates",
        "show_on_website",
    ]

    list_display = [
        "created_at",
        "display_number",
        "name",
        "display_amount",
        Column("frequency", label="How often", accessor="get_frequency_display"),
        "appeal",
        Column("payment_status", label="Payment", accessor="payment_display"),
    ]
    list_filter = [
        "frequency",
        "appeal",
        "payment_status",
        "email_updates",
        "show_on_website",
        "created_at",
    ]
    search_fields = ["name", "email", "phone", "number"]
    search_backend_name = None  # plain database search; pledges aren't in the site search index

    list_export = [
        "created_at",
        "number",
        "amount",
        "currency",
        "get_frequency_display",
        "name",
        "email",
        "phone",
        "appeal",
        "address",
        "postcode",
        "message",
        "email_updates",
        "show_on_website",
        "payment_display",
        "paid_at",
        "paid_with",
    ]
    export_headings = {
        "created_at": "Sent",
        "number": "Pledge number",
        "get_frequency_display": "How often",
        "email_updates": "Email updates",
        "show_on_website": "Show on website",
        "payment_display": "Payment",
        "paid_at": "Paid",
        "paid_with": "Paid with",
    }
    export_filename = "pledges"


class QRCodeIndexView(SnippetIndexView):
    def get_table(self, object_list):
        # Each row's name: all of them in one query, not one per code.
        return super().get_table(QRCode.with_names(object_list))


class QRCodeViewSet(SnippetViewSet):
    """The charity's QR codes, listed like any other records: an Add button when there are none,
    and each row opens its edit page. Only moderators have the permissions (see
    0014_qr_payments), so an editor never sees them. Wagtail's history for each
    code says who added, changed or removed it, and when. Drag a row to put a code first."""

    model = QRCode
    icon = "image"
    menu_label = "QR codes"
    add_to_admin_menu = True
    menu_order = 260
    index_view_class = QRCodeIndexView
    list_display = ["name", "account_name", "account_number"]

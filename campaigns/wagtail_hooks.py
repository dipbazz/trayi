import datetime
from dataclasses import dataclass

from django.db.models import Min, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, ngettext
from wagtail import hooks
from wagtail.admin.ui.components import Component
from wagtail.snippets.models import register_snippet

from campaigns.models import CampaignPage, Payment, PaymentStatus, Pledge, QRCode
from campaigns.views import (
    CONFIRM_PERMISSION,
    PledgeViewSet,
    QRCodeViewSet,
    paid_how,
    to_confirm_list_url,
)
from core.languages import main_language

CLOSING_SOON_DAYS = 14
# The most payments to confirm the dashboard lists; "See all" opens the rest in the Pledges list.
TO_CONFIRM_ROWS = 10


def once_each(appeals):
    """`appeals` with each appeal once, whatever languages it's published in (#195): its copy in
    the site's main language, else its copy in the other language, so an appeal published in one
    language only still counts. The site has two languages (`LANGUAGES`)."""
    in_main_language = Q(locale__language_code=main_language())
    counted = appeals.filter(in_main_language).values("translation_key")
    return appeals.filter(in_main_language | ~Q(translation_key__in=counted))


class FundraisingPanel(Component):
    """Dashboard summary of open appeals, so fundraisers see progress as soon as they log in."""

    name = "fundraising"
    template_name = "campaigns/admin/fundraising_panel.html"
    order = 50

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        today = datetime.date.today()
        open_appeals = once_each(CampaignPage.objects.live().active())
        totals = open_appeals.aggregate(raised=Sum("amount_raised"), target=Sum("target_amount"))
        context.update(
            {
                # The money tag reads the currency from the request's Site settings.
                "request": parent_context["request"],
                "open_count": open_appeals.count(),
                "total_raised": totals["raised"] or 0,
                "total_target": totals["target"] or 0,
                "closing_soon": open_appeals.filter(
                    end_date__lte=today + datetime.timedelta(days=CLOSING_SOON_DAYS)
                ).order_by("end_date"),
            }
        )
        return context


@hooks.register("construct_homepage_panels")
def add_fundraising_panel(request, panels):
    panels.append(FundraisingPanel())


def waited(since, now=None):
    """How long ago, in the admin's language, to the hour: "2 days ago", "3 hours ago". Not
    Django's timesince, whose Nepali catalogue is out of date and would show English."""
    waited_for = (now or timezone.now()) - since
    if waited_for.days:
        return ngettext("%(days)d day ago", "%(days)d days ago", waited_for.days) % {
            "days": waited_for.days
        }
    hours = waited_for.seconds // 3600
    if hours:
        return ngettext("%(hours)d hour ago", "%(hours)d hours ago", hours) % {"hours": hours}
    return gettext("less than an hour ago")


@dataclass
class ToConfirmRow:
    """A pledge To confirm on the dashboard. `payment` is its payment To confirm, or None when it
    has none left (a QR payment marked not found while an older online try is still waiting,
    #385): the row then says so rather than failing the dashboard."""

    pledge: Pledge
    payment: Payment | None

    @property
    def amount(self):
        return (self.payment or self.pledge).display_amount()

    @property
    def paid_by(self):
        return paid_how(self.payment) if self.payment else ""

    @property
    def ago(self):
        return waited(self.payment.created_at) if self.payment else ""

    @property
    def url(self):
        return reverse("pledges:inspect", args=[self.pledge.pk])


@dataclass
class ToConfirm:
    """What the Payments to confirm panel shows: how many pledges are To confirm, the oldest
    TO_CONFIRM_ROWS of them, and whether to show the panel at all."""

    count: int
    rows: list[ToConfirmRow]
    shown: bool

    @property
    def see_all_url(self):
        return to_confirm_list_url()


def payments_to_confirm():
    """The pledges To confirm, the one whose supporter said they paid longest ago first: they've
    waited longest, and their screenshot is deleted first. Reads the pledge's status, as the
    Pledges list's filter does, so the count and "See all" agree (#383). Shown with something
    waiting, or with a QR code set up to say nothing is; a site with neither doesn't take QR
    payments. Three queries at most, however many are waiting."""
    waiting = Pledge.objects.filter(payment_status=PaymentStatus.TO_CONFIRM)
    count = waiting.count()
    if not count:
        return ToConfirm(count=0, rows=[], shown=QRCode.objects.exists())
    to_confirm = Q(payments__status=PaymentStatus.TO_CONFIRM)
    oldest = (
        waiting.annotate(said_paid_at=Min("payments__created_at", filter=to_confirm))
        .order_by(Coalesce("said_paid_at", "created_at"), "pk")
        .prefetch_related(
            Prefetch(
                "payments",
                Payment.objects.filter(status=PaymentStatus.TO_CONFIRM),
                to_attr="to_confirm",
            )
        )[:TO_CONFIRM_ROWS]
    )
    rows = [ToConfirmRow(pledge, next(iter(pledge.to_confirm), None)) for pledge in oldest]
    return ToConfirm(count=count, rows=rows, shown=True)


class PaymentsToConfirmPanel(Component):
    """The supporters who say they've paid by QR, for the team to find in its statement and mark
    paid (#383). First on the dashboard, before Still to write: real money waits on it."""

    name = "payments_to_confirm"
    template_name = "campaigns/admin/payments_to_confirm_panel.html"
    order = 5

    def __init__(self, result):
        self.result = result

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        context["result"] = self.result
        return context


@hooks.register("construct_homepage_panels")
def add_payments_to_confirm_panel(request, panels):
    """For people who can confirm payments (Moderators); editors can't, so they don't see it."""
    if not request.user.has_perm(CONFIRM_PERMISSION):
        return
    result = payments_to_confirm()
    if result.shown:
        panels.append(PaymentsToConfirmPanel(result))


@hooks.register("register_admin_viewset")
def register_pledge_viewset():
    return PledgeViewSet()


@hooks.register("register_log_actions")
def register_gift_actions(actions):
    """The team taking a gift's page for friends down and putting it back (#100), as the pledge's
    history names them."""
    actions.register_action(
        "campaigns.stop_showing", "Stop showing on the website", "Stopped showing on the website"
    )
    actions.register_action(
        "campaigns.show_again", "Show again on the website", "Shown again on the website"
    )


register_snippet(QRCodeViewSet)

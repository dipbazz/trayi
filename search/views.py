from django.core.paginator import Paginator
from django.db.models import Q
from django.template.response import TemplateResponse
from wagtail.contrib.search_promotions.models import Query, SearchPromotion
from wagtail.models import Locale, Page
from wagtail.search.utils import normalise_query_string

from core.limits import over_limit

RESULTS_PER_PAGE = 10


def search(request):
    search_query = request.GET.get("query", "").strip()
    # Results and promotions are in the language being read: /ne/search/ finds Nepali pages (#119).
    locale = Locale.get_active()

    if search_query:
        # public() drops pages behind a password, login or group restriction.
        search_results = Page.objects.live().public().filter(locale=locale).search(search_query)
        # Only reads: Query.get() would save a row for every new word, even past the limit (#352).
        query = Query.objects.filter(query_string=normalise_query_string(search_query)).first()
        # Editors promote a page in each language for the same query; external links show in both.
        promotions = (
            query.editors_picks.filter(
                Q(page__isnull=True) | Q(page__locale=locale)
            ).select_related("page")
            if query
            else SearchPromotion.objects.none()
        )
    else:
        search_results = Page.objects.none()
        promotions = SearchPromotion.objects.none()

    page = Paginator(search_results, RESULTS_PER_PAGE).get_page(request.GET.get("page"))

    # Logged so editors can see what people look for and add promotions: once per search (page 1
    # shown; a page past the last shows the last, page 1 only when the results fit on one), and
    # only while this connection is under its limit, so a script can't fill the database. Past it
    # the page is the same.
    if search_query and page.number == 1 and not over_limit(request, "search"):
        Query.get(search_query).add_hit()

    return TemplateResponse(
        request,
        "search/search.html",
        {
            "search_query": search_query,
            "search_results": page,
            "promotions": promotions,
        },
    )

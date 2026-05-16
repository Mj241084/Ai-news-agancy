from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.search.services import SearchService
from utils.caching import get_or_set_cached, make_cache_key


def _safe_int(raw_value, default=1):
    try:
        return max(int(raw_value), 1)
    except (TypeError, ValueError):
        return default


def _json_response(payload: dict, *, status: int = 200):
    response = JsonResponse(payload, status=status)
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@require_GET
def search_api_view(request):
    query = request.GET.get("q", "")
    page = _safe_int(request.GET.get("page", 1), default=1)

    clean_query, filters, plan = SearchService.parse_search_query(query)

    request_type = (request.GET.get("type") or "").strip().lower()
    request_sort = (request.GET.get("sort") or "").strip().lower()

    if request_type in {"all", "news", "articles"}:
        filters["type"] = request_type

    if request_sort in {"latest", "popular", "team"}:
        filters["sort"] = request_sort
        filters["team_pick"] = request_sort == "team"

    cache_key = make_cache_key(
        "search:api",
        q=clean_query or query,
        page=page,
        type=filters.get("type", "all"),
        sort=filters.get("sort", "latest"),
    )

    result = get_or_set_cached(
        cache_key,
        settings.SEARCH_CACHE_SECONDS,
        lambda: SearchService.run_search(plan, filters, page=page, page_size=settings.SEARCH_PAGE_SIZE),
    )
    result["clean_query"] = clean_query
    return _json_response(result)

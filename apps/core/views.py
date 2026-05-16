from __future__ import annotations

from django.contrib.sitemaps.views import sitemap as django_sitemap_view
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.content.cache_keys import core_home_key, core_popular_key, core_team_picks_key
from apps.content import services as content_services
from apps.core.sitemap_cache import (
    SITEMAP_CACHE_TIMEOUT,
    SITEMAP_XML_CACHE_KEY,
)
from apps.core.sitemaps import sitemaps
from apps.entities.models import RankingList
from apps.search.services import SearchService
from apps.seo.context import build_seo_context
from utils.caching import get_or_set_cached, make_cache_key


def _safe_int(raw_value, default=1):
    try:
        return max(int(raw_value), 1)
    except (TypeError, ValueError):
        return default


def _pagination_with_urls(request, payload: dict) -> dict:
    pagination = {
        "page": payload.get("page", 1),
        "page_size": payload.get("page_size", 15),
        "total": payload.get("total", 0),
        "pages": payload.get("pages", 1),
        "has_next": payload.get("has_next", False),
        "has_previous": payload.get("has_previous", False),
        "next_url": None,
        "prev_url": None,
    }

    if pagination["has_previous"]:
        params = request.GET.copy()
        params["page"] = pagination["page"] - 1
        pagination["prev_url"] = f"?{params.urlencode()}"

    if pagination["has_next"]:
        params = request.GET.copy()
        params["page"] = pagination["page"] + 1
        pagination["next_url"] = f"?{params.urlencode()}"

    return pagination


def _serialize_active_ranking() -> dict | None:
    ranking = (
        RankingList.objects.filter(is_active=True)
        .prefetch_related("entries")
        .order_by("-updated_at", "-id")
        .first()
    )
    if not ranking:
        return None

    dynamic_columns = []
    raw_columns = ranking.columns if isinstance(ranking.columns, list) else []
    for raw in raw_columns:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        label = str(raw.get("label") or key).strip() or key
        dynamic_columns.append({"key": key, "label": label})

    entries = []
    for entry in ranking.entries.all():
        row = {
            "rank": entry.rank,
            "name": entry.name,
            "score": entry.score,
            "data": entry.data if isinstance(entry.data, dict) else {},
        }
        entries.append(row)

    return {
        "id": ranking.id,
        "title": ranking.title,
        "kind": ranking.kind,
        "columns": dynamic_columns,
        "entries": entries,
    }


@ensure_csrf_cookie
def home_view(request):
    page = _safe_int(request.GET.get("page", 1), default=1)

    cache_key = core_home_key(page=page)

    def _build_payload():
        latest = content_services.list_latest(page=page, page_size=15)
        popular = content_services.list_popular(page=1, page_size=10)
        team = content_services.list_team_picks(page=1, page_size=10)
        latest_videos = content_services.list_latest_videos(limit=6)
        ranking = _serialize_active_ranking()
        return {
            "latest": latest,
            "popular": popular,
            "team": team,
            "latest_videos": latest_videos,
            "ranking": ranking,
        }

    payload = get_or_set_cached(cache_key, settings.PAGE_CACHE_SECONDS, _build_payload)

    context = {
        "items": payload["latest"]["items"],
        "popular_items": payload["popular"]["items"],
        "team_pick_items": payload["team"]["items"],
        "latest_videos": payload["latest_videos"],
        "ranking": payload["ranking"],
        "pagination": _pagination_with_urls(request, payload["latest"]),
        "active_nav": "home",
        "seo": build_seo_context(request, page_type="home"),
    }
    return render(request, "pages/home.html", context)


def popular_view(request):
    page = _safe_int(request.GET.get("page", 1), default=1)

    cache_key = core_popular_key(page=page)

    payload = get_or_set_cached(
        cache_key,
        settings.PAGE_CACHE_SECONDS,
        lambda: content_services.list_popular(page=page, page_size=15),
    )

    context = {
        "items": payload["items"],
        "pagination": _pagination_with_urls(request, payload),
        "active_nav": "popular",
        "seo": build_seo_context(request, page_type="popular"),
    }
    return render(request, "pages/list_popular.html", context)


def team_picks_view(request):
    page = _safe_int(request.GET.get("page", 1), default=1)

    cache_key = core_team_picks_key(page=page)

    payload = get_or_set_cached(
        cache_key,
        settings.PAGE_CACHE_SECONDS,
        lambda: content_services.list_team_picks(page=page, page_size=15),
    )

    context = {
        "items": payload["items"],
        "pagination": _pagination_with_urls(request, payload),
        "active_nav": "team-picks",
        "seo": build_seo_context(request, page_type="team_picks"),
    }
    return render(request, "pages/list_team_picks.html", context)


def search_view(request):
    query = (request.GET.get("q") or "").strip()
    page = _safe_int(request.GET.get("page", 1), default=1)

    requested_type = (request.GET.get("type") or "").strip().lower()
    requested_sort = (request.GET.get("sort") or "").strip().lower()

    clean_query, filters, plan = SearchService.parse_search_query(query)
    if requested_type in {"all", "news", "articles"}:
        filters["type"] = requested_type
    if requested_sort in {"latest", "popular", "team"}:
        filters["sort"] = requested_sort
        filters["team_pick"] = requested_sort == "team"

    if query:
        cache_key = make_cache_key(
            "core:search",
            q=clean_query or query,
            page=page,
            type=filters.get("type", "all"),
            sort=filters.get("sort", "latest"),
        )
        payload = get_or_set_cached(
            cache_key,
            settings.SEARCH_CACHE_SECONDS,
            lambda: SearchService.run_search(plan, filters, page=page, page_size=settings.SEARCH_PAGE_SIZE),
        )
    else:
        payload = {
            "query": "",
            "filters": {"type": filters.get("type", "all"), "sort": filters.get("sort", "latest")},
            "page": page,
            "page_size": settings.SEARCH_PAGE_SIZE,
            "total": 0,
            "items": [],
        }

    page_size = int(payload.get("page_size") or settings.SEARCH_PAGE_SIZE)
    total = int(payload.get("total") or 0)
    pages = max((total + page_size - 1) // page_size, 1)

    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "has_previous": page > 1,
        "has_next": page < pages,
        "prev_url": None,
        "next_url": None,
    }

    if pagination["has_previous"]:
        params = request.GET.copy()
        params["page"] = page - 1
        pagination["prev_url"] = f"?{params.urlencode()}"
    if pagination["has_next"]:
        params = request.GET.copy()
        params["page"] = page + 1
        pagination["next_url"] = f"?{params.urlencode()}"

    context = {
        "query": query,
        "items": payload.get("items", []),
        "total_results": total,
        "filters": {
            "content_type": payload.get("filters", {}).get("type", filters.get("type", "all")),
            "sort": payload.get("filters", {}).get("sort", filters.get("sort", "latest")),
        },
        "pagination": pagination,
        "active_nav": "search",
        "seo": build_seo_context(
            request,
            page_type="search",
            extras={
                "title": f"جستجو: {query}" if query else "",
                "sort": payload.get("filters", {}).get("sort", filters.get("sort", "latest")),
            },
        ),
    }
    return render(request, "pages/search.html", context)


def robots_txt_view(request):
    cache_key = make_cache_key("seo:robots-txt")

    def _build_body():
        lines = [
            "User-agent: *",
            "Disallow: /staff/",
            "Disallow: /ajax/",
            "Disallow: /api/",
            "Disallow: /auth/",
            "Disallow: /admin/",
            f"Sitemap: {settings.SITE_BASE_URL}/sitemap.xml",
        ]
        return "\n".join(lines) + "\n"

    body = get_or_set_cached(cache_key, 60 * 60 * 24, _build_body)
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def sitemap_xml_view(request):
    cached_xml = cache.get(SITEMAP_XML_CACHE_KEY)
    if cached_xml is not None:
        return HttpResponse(cached_xml, content_type="application/xml; charset=utf-8")

    response = django_sitemap_view(request, sitemaps=sitemaps)
    response.render()
    if response.status_code == 200:
        cache.set(SITEMAP_XML_CACHE_KEY, response.content, timeout=SITEMAP_CACHE_TIMEOUT)
    return response


def about_view(request):
    context = {
        "active_nav": "",
        "seo": build_seo_context(request, page_type="about"),
    }
    return render(request, "pages/about.html", context)


def contact_view(request):
    context = {
        "active_nav": "",
        "seo": build_seo_context(request, page_type="contact"),
    }
    return render(request, "pages/contact.html", context)


def terms_view(request):
    context = {
        "active_nav": "",
        "seo": build_seo_context(request, page_type="terms"),
    }
    return render(request, "pages/terms.html", context)


def privacy_view(request):
    context = {
        "active_nav": "",
        "seo": build_seo_context(request, page_type="privacy"),
    }
    return render(request, "pages/privacy.html", context)

from __future__ import annotations

from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.content import services as content_services
from apps.seo.context import build_seo_context
from apps.taxonomy.cache_keys import category_detail_key, category_index_key, tag_detail_key
from apps.taxonomy.models import Category, Tag
from utils.caching import get_or_set_cached


PAGE_SIZE = 15


def _safe_int(raw_value, default=1):
    try:
        return max(int(raw_value), 1)
    except (TypeError, ValueError):
        return default


def _pagination_with_urls(request, payload: dict) -> dict:
    pagination = {
        "page": payload.get("page", 1),
        "page_size": payload.get("page_size", PAGE_SIZE),
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


def category_index_view(request):
    cache_key = category_index_key()
    categories = get_or_set_cached(
        cache_key,
        settings.PAGE_CACHE_SECONDS,
        content_services.build_category_tree,
    )

    context = {
        "categories": categories,
        "active_nav": "categories",
        "seo": build_seo_context(
            request,
            page_type="category_index",
            extras={
                "breadcrumb_items": [[("خانه", reverse("core:home")), ("دسته‌بندی‌ها", reverse("taxonomy:category_index"))]]
            },
        ),
    }
    return render(request, "pages/categories.html", context)


def category_detail_view(request, category_slug: str):
    category = get_object_or_404(Category, slug=category_slug, is_active=True)

    page = _safe_int(request.GET.get("page", 1), default=1)
    type_filter = (request.GET.get("type") or "all").strip().lower()
    if type_filter not in {"all", "news", "articles"}:
        type_filter = "all"

    sort_filter = (request.GET.get("sort") or "latest").strip().lower()
    if sort_filter not in {"latest", "popular", "team"}:
        sort_filter = "latest"

    include_sub = (request.GET.get("sub") or "1").strip() == "1"

    cache_key = category_detail_key(
        slug=category.slug,
        page=page,
        type=type_filter,
        sort=sort_filter,
        sub=1 if include_sub else 0,
    )

    def _build_payload():
        queryset = content_services.get_category_article_queryset(category, include_subcategories=include_sub)
        queryset = content_services.apply_type_filter(queryset, type_filter)

        if sort_filter == "popular":
            main = content_services.list_popular(queryset=queryset, page=page, page_size=PAGE_SIZE, primary_category_id=category.id)
        elif sort_filter == "team":
            main = content_services.list_team_picks(queryset=queryset, page=page, page_size=PAGE_SIZE, primary_category_id=category.id)
        else:
            main = content_services.list_latest(queryset=queryset, page=page, page_size=PAGE_SIZE, primary_category_id=category.id)

        subcats = list(
            Category.objects.filter(parent=category, is_active=True)
            .order_by("order", "title")
            .values("id", "title", "slug")
        )
        return {
            "main": main,
            "latest": content_services.list_latest(queryset=queryset, page=1, page_size=10, primary_category_id=category.id),
            "popular": content_services.list_popular(queryset=queryset, page=1, page_size=10, primary_category_id=category.id),
            "team": content_services.list_team_picks(queryset=queryset, page=1, page_size=10, primary_category_id=category.id),
            "subcategories_nav": subcats,
        }

    payload = get_or_set_cached(cache_key, settings.PAGE_CACHE_SECONDS, _build_payload)

    context = {
        "category": {
            "id": category.id,
            "name": category.title,
            "title": category.title,
            "slug": category.slug,
            "description": category.description,
        },
        "items": payload["main"]["items"],
        "latest_items": payload["latest"]["items"],
        "popular_items": payload["popular"]["items"],
        "team_pick_items": payload["team"]["items"],
        "pagination": _pagination_with_urls(request, payload["main"]),
        "filters": {
            "content_type": type_filter,
            "sort": sort_filter,
            "include_subcats": include_sub,
        },
        "subcategories_nav": [
            {"id": row["id"], "title": row["title"], "name": row["title"], "slug": row["slug"], "url": reverse("taxonomy:category_detail", kwargs={"category_slug": row["slug"]})}
            for row in payload.get("subcategories_nav", [])
        ],
        "active_nav": "categories",
        "seo": build_seo_context(
            request,
            page_type="category_detail",
            obj=category,
            extras={
                "sort": sort_filter,
                "breadcrumb_items": [
                    [
                        ("خانه", reverse("core:home")),
                        ("دسته‌بندی‌ها", reverse("taxonomy:category_index")),
                        (category.title, category.get_absolute_url()),
                    ]
                ],
            },
        ),
    }
    return render(request, "pages/category_detail.html", context)


def tag_detail_view(request, tag_slug: str):
    tag = get_object_or_404(Tag, slug=tag_slug, is_active=True)
    page = _safe_int(request.GET.get("page", 1), default=1)
    type_filter = (request.GET.get("type") or "all").strip().lower()
    if type_filter not in {"all", "news", "articles"}:
        type_filter = "all"
    sort_filter = (request.GET.get("sort") or "latest").strip().lower()
    if sort_filter not in {"latest", "popular", "team"}:
        sort_filter = "latest"

    cache_key = tag_detail_key(
        slug=tag.slug,
        page=page,
        sort=sort_filter,
        type=type_filter,
    )

    def _build_payload():
        queryset = content_services.get_tag_article_queryset(tag)
        queryset = content_services.apply_type_filter(queryset, type_filter)
        if sort_filter == "popular":
            listing = content_services.list_popular(queryset=queryset, page=page, page_size=PAGE_SIZE)
        elif sort_filter == "team":
            listing = content_services.list_team_picks(queryset=queryset, page=page, page_size=PAGE_SIZE)
        else:
            listing = content_services.list_latest(queryset=queryset, page=page, page_size=PAGE_SIZE)
        related_tags = list(
            Tag.objects.filter(is_active=True)
            .exclude(id=tag.id)
            .order_by("title")
            .values("title", "slug")[:10]
        )
        return {"listing": listing, "related_tags": related_tags}

    payload = get_or_set_cached(cache_key, settings.PAGE_CACHE_SECONDS, _build_payload)

    context = {
        "tag": {
            "id": tag.id,
            "name": tag.title,
            "title": tag.title,
            "slug": tag.slug,
            "description": tag.description,
        },
        "items": payload["listing"]["items"],
        "pagination": _pagination_with_urls(request, payload["listing"]),
        "filters": {"content_type": type_filter, "sort": sort_filter},
        "related_tags": [
            {"name": row["title"], "title": row["title"], "slug": row["slug"]}
            for row in payload["related_tags"]
        ],
        "active_nav": "categories",
        "seo": build_seo_context(
            request,
            page_type="tag_detail",
            obj=tag,
            extras={
                "title": f"#{tag.title} | {settings.SITE_NAME}",
                "sort": sort_filter,
                "breadcrumb_items": [
                    [
                        ("خانه", reverse("core:home")),
                        ("برچسب", tag.get_absolute_url()),
                    ]
                ],
            },
        ),
    }
    return render(request, "pages/tag_detail.html", context)

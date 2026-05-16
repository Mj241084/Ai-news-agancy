from __future__ import annotations

from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.content import services as content_services
from apps.entities.models import Entity
from apps.seo.context import build_seo_context
from apps.taxonomy.cache_keys import entity_detail_key
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


def entity_detail_view(request, entity_type: str, slug: str):
    entity = get_object_or_404(Entity, type=entity_type, slug=slug, is_active=True)
    page = _safe_int(request.GET.get("page", 1), default=1)

    cache_key = entity_detail_key(type=entity.type, slug=entity.slug, page=page)

    payload = get_or_set_cached(
        cache_key,
        settings.PAGE_CACHE_SECONDS,
        lambda: content_services.list_latest(
            queryset=content_services.get_entity_article_queryset(entity),
            page=page,
            page_size=PAGE_SIZE,
        ),
    )

    context = {
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "slug": entity.slug,
            "type": entity.type,
            "description": entity.description,
        },
        "items": payload["items"],
        "pagination": _pagination_with_urls(request, payload),
        "active_nav": "categories",
        "seo": build_seo_context(
            request,
            page_type="entity_detail",
            obj=entity,
            extras={
                "breadcrumb_items": [
                    [
                        ("خانه", reverse("core:home")),
                        ("موجودیت", entity.get_absolute_url()),
                    ]
                ]
            },
        ),
    }
    return render(request, "pages/entity_detail.html", context)

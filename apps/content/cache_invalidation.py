from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from apps.core.sitemap_cache import invalidate_sitemap_cache
from apps.content.cache_keys import (
    article_main_key,
    content_ajax_comments_key,
    content_ajax_related_key,
    content_ajax_stats_key,
    content_article_list_key,
    content_news_list_key,
    core_home_key,
    core_popular_key,
    core_team_picks_key,
)
from apps.taxonomy.cache_keys import category_detail_key, category_index_key
from apps.taxonomy.models import Category


def _delete_keys(keys: list[str]) -> None:
    for key in keys:
        cache.delete(key)


def invalidate_article_cache(article, *, previous_slug: str | None = None) -> None:
    invalidate_sitemap_cache()

    slugs = {article.slug}
    if previous_slug and previous_slug != article.slug:
        slugs.add(previous_slug)

    keys = []
    for slug in slugs:
        keys.append(article_main_key(slug))
        keys.append(content_ajax_stats_key(slug=slug, days="all"))
        keys.append(content_ajax_stats_key(slug=slug, days=settings.POPULAR_LOOKBACK_DAYS))
        keys.append(content_ajax_comments_key(slug=slug, page=1))
        keys.append(content_ajax_related_key(slug=slug, limit=10))
        keys.append(content_ajax_related_key(slug=slug, limit=20))

    _delete_keys(keys)


def invalidate_listing_caches(
    article,
    *,
    previous_category_ids: set[int] | None = None,
    previous_is_team_pick: bool | None = None,
) -> None:
    keys = [
        core_home_key(page=1),
        core_popular_key(page=1),
        category_index_key(),
    ]

    for sort in ("latest", "popular", "team"):
        keys.append(content_news_list_key(page=1, sort=sort))
        keys.append(content_article_list_key(page=1, sort=sort))

    team_related = bool(article.is_team_pick or (previous_is_team_pick is True))
    if team_related:
        keys.append(core_team_picks_key(page=1))

    current_category_ids = set(
        article.article_categories.values_list("category_id", flat=True)
    )
    affected_category_ids = set(previous_category_ids or set()) | current_category_ids

    if affected_category_ids:
        slug_by_id = {
            row["id"]: row["slug"]
            for row in Category.objects.filter(id__in=affected_category_ids).values("id", "slug")
        }
        for category_id in affected_category_ids:
            slug = slug_by_id.get(category_id)
            if not slug:
                continue
            for sort in ("latest", "popular", "team"):
                for type_filter in ("all", "news", "articles"):
                    for sub in (0, 1):
                        keys.append(
                            category_detail_key(
                                slug=slug,
                                page=1,
                                type=type_filter,
                                sort=sort,
                                sub=sub,
                            )
                        )

    _delete_keys(keys)


def invalidate_interaction_caches(article, *, event_type: str | None = None) -> None:
    keys = [
        content_ajax_stats_key(slug=article.slug, days="all"),
        content_ajax_stats_key(slug=article.slug, days=settings.POPULAR_LOOKBACK_DAYS),
    ]

    normalized_event = (event_type or "").strip().lower()
    if normalized_event in {"rating", "share"}:
        keys.extend(
            [
                core_home_key(page=1),
                core_popular_key(page=1),
                content_news_list_key(page=1, sort="popular"),
                content_article_list_key(page=1, sort="popular"),
            ]
        )

    _delete_keys(keys)


def invalidate_comment_caches(article) -> None:
    keys = [
        content_ajax_comments_key(slug=article.slug, page=1),
        content_ajax_stats_key(slug=article.slug, days="all"),
        content_ajax_stats_key(slug=article.slug, days=settings.POPULAR_LOOKBACK_DAYS),
    ]
    _delete_keys(keys)

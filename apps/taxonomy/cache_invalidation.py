from __future__ import annotations

from django.core.cache import cache

from apps.core.sitemap_cache import invalidate_sitemap_cache
from apps.taxonomy.cache_keys import (
    category_detail_key,
    category_index_key,
    entity_detail_key,
    tag_detail_key,
)
from apps.taxonomy.models import Category


def _delete_keys(keys: list[str]) -> None:
    for key in keys:
        cache.delete(key)


def invalidate_category_index_cache() -> None:
    cache.delete(category_index_key())


def invalidate_category_detail_caches_for_slug(slug: str) -> None:
    keys = []
    for sort in ("latest", "popular", "team"):
        for content_type in ("all", "news", "articles"):
            for sub in (0, 1):
                keys.append(
                    category_detail_key(
                        slug=slug,
                        page=1,
                        sort=sort,
                        type=content_type,
                        sub=sub,
                    )
                )
    _delete_keys(keys)


def invalidate_tag_detail_caches_for_slug(slug: str) -> None:
    keys = []
    for sort in ("latest", "popular", "team"):
        for content_type in ("all", "news", "articles"):
            keys.append(
                tag_detail_key(
                    slug=slug,
                    page=1,
                    sort=sort,
                    type=content_type,
                )
            )
    _delete_keys(keys)


def invalidate_entity_detail_caches_for_slug(entity_type: str, slug: str) -> None:
    cache.delete(entity_detail_key(type=entity_type, slug=slug, page=1))


def invalidate_taxonomy_on_category_change(
    category: Category,
    *,
    previous_slug: str | None = None,
    previous_parent_id: int | None = None,
) -> None:
    invalidate_sitemap_cache()
    invalidate_category_index_cache()

    affected_slugs = {category.slug}
    if previous_slug:
        affected_slugs.add(previous_slug)

    parent_ids = {category.parent_id}
    if previous_parent_id is not None:
        parent_ids.add(previous_parent_id)

    parent_ids = {parent_id for parent_id in parent_ids if parent_id}
    if parent_ids:
        for slug in Category.objects.filter(id__in=parent_ids).values_list("slug", flat=True):
            affected_slugs.add(slug)

    for child_slug in Category.objects.filter(parent_id=category.id).values_list("slug", flat=True):
        affected_slugs.add(child_slug)

    for slug in affected_slugs:
        invalidate_category_detail_caches_for_slug(slug)


def invalidate_taxonomy_on_tag_change(tag, *, previous_slug: str | None = None) -> None:
    invalidate_sitemap_cache()
    affected_slugs = {tag.slug}
    if previous_slug:
        affected_slugs.add(previous_slug)
    for slug in affected_slugs:
        invalidate_tag_detail_caches_for_slug(slug)


def invalidate_taxonomy_on_entity_change(
    entity,
    *,
    previous_slug: str | None = None,
    previous_type: str | None = None,
) -> None:
    invalidate_sitemap_cache()
    pairs = {(entity.type, entity.slug)}
    if previous_slug and previous_type:
        pairs.add((previous_type, previous_slug))
    for entity_type, slug in pairs:
        invalidate_entity_detail_caches_for_slug(entity_type, slug)

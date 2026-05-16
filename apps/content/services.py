from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Case, When, Value, IntegerField
from django.db.models import Prefetch
from django.urls import reverse

from apps.content.cache_keys import article_main_key
from apps.content.models import Article, ArticleCategory, ArticleEntity, ArticleSource
from apps.content.utils import render_markdown_safe
from apps.interactions.services import get_popular_article_scores
from apps.taxonomy.models import Category, Tag


def _pagination_payload(page_obj, paginator, page_size: int) -> dict:
    return {
        "page": page_obj.number,
        "page_size": page_size,
        "total": paginator.count,
        "pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }


def _estimate_read_time_minutes(text: str) -> int:
    words = len((text or "").split())
    if words <= 0:
        return 1
    return max(1, int(math.ceil(words / 220)))


def get_published_queryset():
    return Article.objects.filter(
        status=Article.STATUS_PUBLISHED,
        published_at__isnull=False,
    )


def apply_type_filter(queryset, type_filter: str):
    if type_filter == "news":
        return queryset.filter(content_type=Article.CONTENT_SHORT_NEWS)
    if type_filter == "articles":
        return queryset.filter(content_type__in=[Article.CONTENT_POST, Article.CONTENT_ARTICLE])
    return queryset


def serialize_article_summary(article: Article, *, popularity_score: float | None = None) -> dict:
    category_links = list(getattr(article, 'article_categories', []).all()) if hasattr(article, 'article_categories') else []
    categories = [
        {
            "id": rel.category.id,
            "title": rel.category.title,
            "name": rel.category.title,
            "slug": rel.category.slug,
            "url": rel.category.get_absolute_url(),
        }
        for rel in category_links
        if getattr(rel, 'category', None)
    ]

    item = {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "url": article.get_absolute_url(),
        "excerpt": article.excerpt,
        "content_type": article.content_type,
        "is_team_pick": article.is_team_pick,
        "published_at": article.published_at,
        "hero_image": article.hero_image or None,
        "thumbnail": article.thumbnail or None,
        "video_url": article.video_url or None,
        "video_thumbnail": article.video_thumbnail or None,
        "read_time": _estimate_read_time_minutes(article.body),
        "categories": categories,
    }

    if popularity_score is not None:
        item["popularity_score"] = round(float(popularity_score), 2)
        item["view_count"] = int(popularity_score)

    return item


def _article_only_fields(queryset):
    return queryset.only(
        "id",
        "title",
        "slug",
        "excerpt",
        "body",
        "content_type",
        "status",
        "language",
        "hero_image",
        "thumbnail",
        "video_url",
        "video_thumbnail",
        "published_at",
        "updated_at",
        "seo_title",
        "seo_description",
        "canonical_path",
        "meta_robots",
        "is_team_pick",
    ).prefetch_related(
        Prefetch(
            "article_categories",
            queryset=ArticleCategory.objects.select_related("category").order_by(
                "-is_primary",
                "-weight",
                "category__order",
                "category__title",
            ),
        )
    )


def get_article_main_cached(slug: str) -> dict | None:
    cache_key = article_main_key(slug)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    article = (
        get_published_queryset()
        .only(
            "id",
            "title",
            "slug",
            "excerpt",
            "body",
            "content_type",
            "status",
            "language",
            "hero_image",
            "thumbnail",
            "video_url",
            "video_thumbnail",
            "published_at",
            "updated_at",
            "seo_title",
            "seo_description",
            "canonical_path",
            "meta_robots",
            "is_team_pick",
            "goals",
        )
        .prefetch_related(
            Prefetch(
                "article_categories",
                queryset=ArticleCategory.objects.select_related("category").order_by(
                    "-is_primary",
                    "-weight",
                    "category__order",
                    "category__title",
                ),
            ),
            "tags",
            Prefetch(
                "article_entities",
                queryset=ArticleEntity.objects.select_related("entity").annotate(
                    _role_rank=Case(
                        When(role=ArticleEntity.ROLE_MAIN, then=Value(0)),
                        When(role=ArticleEntity.ROLE_TARGET, then=Value(1)),
                        When(role=ArticleEntity.ROLE_AUTHOR, then=Value(2)),
                        default=Value(3),
                        output_field=IntegerField(),
                    )
                ).order_by("_role_rank", "-importance", "entity__name"),
            ),
            Prefetch(
                "article_sources",
                queryset=ArticleSource.objects.select_related("source").order_by("source__name"),
            ),
        )
        .filter(slug=slug)
        .first()
    )
    if not article:
        return None

    categories = [
        {
            "id": rel.category.id,
            "title": rel.category.title,
            "name": rel.category.title,
            "slug": rel.category.slug,
            "url": rel.category.get_absolute_url(),
            "is_primary": bool(rel.is_primary),
            "weight": float(rel.weight or 1.0),
        }
        for rel in article.article_categories.all()
        if rel.category
    ]

    sources = [
        {
            "id": rel.id,
            "original_url": rel.original_url,
            "note": rel.note,
            "confidence": rel.confidence,
            "source": {
                "id": rel.source_id,
                "name": rel.source.name,
                "url": rel.source.url,
                "type": rel.source.type,
                "type_label": rel.source.get_type_display(),
            },
        }
        for rel in article.article_sources.all()
        if rel.source and rel.source.is_active
    ]

    data = {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "url": article.get_absolute_url(),
        "excerpt": article.excerpt,
        "body": article.body,
        "body_html": render_markdown_safe(article.body),
        "content_type": article.content_type,
        "language": article.language,
        "hero_image": article.hero_image or None,
        "thumbnail": article.thumbnail or None,
        "video_url": article.video_url or None,
        "video_thumbnail": article.video_thumbnail or None,
        "published_at": article.published_at,
        "updated_at": article.updated_at,
        "seo_title": article.seo_title,
        "seo_description": article.seo_description,
        "canonical_path": article.canonical_path,
        "meta_robots": article.meta_robots,
        "is_team_pick": article.is_team_pick,
        "read_time": _estimate_read_time_minutes(article.body),
        "categories": categories,
        "tags": [{"id": t.id, "title": t.title, "slug": t.slug} for t in article.tags.all()],
        "entities": [
            {
                "id": rel.entity.id,
                "name": rel.entity.name,
                "slug": rel.entity.slug,
                "type": rel.entity.type,
                "role": rel.role,
                "role_label": {
                    ArticleEntity.ROLE_MAIN: "اصلی",
                    ArticleEntity.ROLE_TARGET: "هدف/موضوع",
                    ArticleEntity.ROLE_AUTHOR: "نویسنده",
                    ArticleEntity.ROLE_MENTIONED: "اشاره‌شده",
                }.get(rel.role, rel.role),
                "importance": float(rel.importance or 1.0),
            }
            for rel in article.article_entities.all()
            if rel.entity and rel.entity.is_active
        ],
        "sources": sources,
        "goals": list(getattr(article, "goals", []) or []),
    }
    cache.set(cache_key, data, timeout=settings.ARTICLE_MAIN_CACHE_SECONDS)
    return data


def list_latest(*, queryset=None, page: int = 1, page_size: int = 15, primary_category_id: int | None = None) -> dict:
    qs = queryset if queryset is not None else get_published_queryset()
    qs = _article_only_fields(qs)
    if primary_category_id:
        primary_exists = ArticleCategory.objects.filter(
            article_id=OuterRef('pk'),
            category_id=primary_category_id,
            is_primary=True,
        )
        qs = qs.annotate(primary_match=Exists(primary_exists)).order_by('-primary_match', '-published_at', '-id')
    else:
        qs = qs.order_by('-published_at', '-id')

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    return {
        **_pagination_payload(page_obj, paginator, page_size),
        "items": [serialize_article_summary(article) for article in page_obj.object_list],
    }


def list_team_picks(*, queryset=None, page: int = 1, page_size: int = 15, primary_category_id: int | None = None) -> dict:
    qs = queryset if queryset is not None else get_published_queryset()
    qs = qs.filter(is_team_pick=True)
    return list_latest(queryset=qs, page=page, page_size=page_size, primary_category_id=primary_category_id)


def list_latest_videos(*, limit: int = 6) -> list[dict]:
    qs = (
        _article_only_fields(get_published_queryset())
        .exclude(video_url__isnull=True)
        .exclude(video_url="")
        .order_by("-published_at", "-id")
    )
    return [serialize_article_summary(article) for article in qs[:limit]]


def list_popular(
    *,
    queryset=None,
    page: int = 1,
    page_size: int = 15,
    days: int | None = None,
    candidate_limit: int | None = None,
    primary_category_id: int | None = None,
) -> dict:
    qs = queryset if queryset is not None else get_published_queryset()
    qs = _article_only_fields(qs)
    if primary_category_id:
        primary_exists = ArticleCategory.objects.filter(
            article_id=OuterRef('pk'),
            category_id=primary_category_id,
            is_primary=True,
        )
        qs = qs.annotate(primary_match=Exists(primary_exists)).order_by('-primary_match', '-published_at', '-id')
    else:
        qs = qs.order_by('-published_at', '-id')

    candidate_limit = candidate_limit or settings.POPULAR_CANDIDATE_LIMIT
    candidate_articles = list(qs[:candidate_limit])

    if not candidate_articles:
        empty_paginator = Paginator([], page_size)
        empty_page = empty_paginator.get_page(page)
        return {
            **_pagination_payload(empty_page, empty_paginator, page_size),
            "items": [],
        }

    candidate_ids = [article.id for article in candidate_articles]
    score_map = get_popular_article_scores(
        article_ids=candidate_ids,
        days=days,
    )

    if not score_map:
        if primary_category_id:
            candidate_articles = sorted(
                candidate_articles,
                key=lambda a: (1 if bool(getattr(a, 'primary_match', False)) else 0, a.published_at or 0, a.id),
                reverse=True,
            )
        paginator = Paginator(candidate_articles, page_size)
        page_obj = paginator.get_page(page)
        return {
            **_pagination_payload(page_obj, paginator, page_size),
            "items": [serialize_article_summary(article, popularity_score=0) for article in page_obj.object_list],
        }

    ranked_articles = sorted(
        candidate_articles,
        key=lambda article: (
            1 if bool(getattr(article, 'primary_match', False)) else 0,
            float(score_map.get(article.id, 0)),
            article.published_at or 0,
            article.id,
        ),
        reverse=True,
    )

    paginator = Paginator(ranked_articles, page_size)
    page_obj = paginator.get_page(page)

    return {
        **_pagination_payload(page_obj, paginator, page_size),
        "items": [
            serialize_article_summary(article, popularity_score=score_map.get(article.id, 0))
            for article in page_obj.object_list
        ],
    }


def get_category_descendant_ids(category_id: int) -> list[int]:
    rows = Category.objects.filter(is_active=True).values("id", "parent_id")
    children_map = defaultdict(list)
    for row in rows:
        children_map[row["parent_id"]].append(row["id"])

    result = []
    stack = [category_id]
    visited = set()

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        result.append(current)
        stack.extend(children_map.get(current, []))

    return result


def get_category_article_queryset(category: Category, include_subcategories: bool = False):
    category_ids = [category.id]
    if include_subcategories:
        category_ids = get_category_descendant_ids(category.id)

    return get_published_queryset().filter(
        article_categories__category_id__in=category_ids,
    ).distinct()


def get_entity_article_queryset(entity):
    return get_published_queryset().filter(article_entities__entity=entity).distinct()


def get_tag_article_queryset(tag: Tag):
    return get_published_queryset().filter(article_tags__tag=tag).distinct()


def build_category_tree() -> list[dict]:
    categories = list(
        Category.objects.filter(is_active=True)
        .order_by("order", "title")
        .values("id", "title", "slug", "description", "parent_id")
    )

    article_count_rows = (
        ArticleCategory.objects.filter(
            article__status=Article.STATUS_PUBLISHED,
            article__published_at__isnull=False,
        )
        .values("category_id")
        .annotate(count=Count("article_id", distinct=True))
    )
    article_counts = {row["category_id"]: row["count"] for row in article_count_rows}

    children_map: dict[int | None, list[dict]] = defaultdict(list)
    for category in categories:
        children_map[category["parent_id"]].append(
            {
                "id": category["id"],
                "title": category["title"],
                "name": category["title"],
                "slug": category["slug"],
                "description": category["description"],
                "url": reverse("taxonomy:category_detail", kwargs={"category_slug": category["slug"]}),
                "article_count": int(article_counts.get(category["id"], 0)),
                "children": [],
            }
        )

    def attach_children(nodes: Iterable[dict]):
        for node in nodes:
            node_children = children_map.get(node["id"], [])
            node["children"] = node_children
            attach_children(node_children)

    roots = children_map.get(None, [])
    attach_children(roots)
    return roots

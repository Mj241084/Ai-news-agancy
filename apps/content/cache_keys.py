from __future__ import annotations

from utils.caching import make_cache_key


def article_main_key(slug: str) -> str:
    return make_cache_key("article:main", slug=slug)


def content_news_list_key(*, page: int = 1, sort: str = "latest") -> str:
    return make_cache_key("content:news", page=page, sort=sort)


def content_article_list_key(*, page: int = 1, sort: str = "latest") -> str:
    return make_cache_key("content:article-list", page=page, sort=sort)


def content_ajax_stats_key(*, slug: str, days: str | int = "all") -> str:
    return make_cache_key("content:ajax:stats", slug=slug, days=days)


def content_ajax_comments_key(*, slug: str, page: int = 1) -> str:
    return make_cache_key("content:ajax:comments", slug=slug, page=page)


def content_ajax_related_key(*, slug: str, limit: int = 10) -> str:
    return make_cache_key("content:ajax:related", slug=slug, limit=limit)


def core_home_key(*, page: int = 1) -> str:
    return make_cache_key("core:home", page=page)


def core_popular_key(*, page: int = 1) -> str:
    return make_cache_key("core:popular", page=page)


def core_team_picks_key(*, page: int = 1) -> str:
    return make_cache_key("core:team-picks", page=page)

from __future__ import annotations
from django.conf import settings

from apps.content.models import Article
from apps.seo.utils import absolute_url, strip_html, truncate


def build_meta_title(article: Article) -> str:
    if article.seo_title:
        return article.seo_title
    return f"{article.title} | {settings.SITE_NAME}"


def build_meta_description(article: Article, max_length: int = 160) -> str:
    if article.seo_description:
        return article.seo_description
    if article.excerpt:
        return truncate(strip_html(article.excerpt), max_length)
    return truncate(strip_html(article.body), max_length)


def build_canonical_url(article: Article) -> str:
    canonical_path = article.canonical_path or article.get_absolute_url()
    return absolute_url(settings.SITE_BASE_URL, canonical_path)


def build_robots(article: Article) -> str:
    if article.status == Article.STATUS_PUBLISHED:
        return article.meta_robots or "index,follow"
    return "noindex,follow"


def build_open_graph(article: Article) -> dict:
    image_url = ""
    if article.hero_image:
        image_url = absolute_url(settings.SITE_BASE_URL, article.hero_image)

    return {
        "og:type": "article",
        "og:title": build_meta_title(article),
        "og:description": build_meta_description(article),
        "og:url": build_canonical_url(article),
        "og:site_name": settings.SITE_NAME,
        "og:image": image_url,
    }


def build_twitter_meta(article: Article) -> dict:
    image_url = ""
    if article.hero_image:
        image_url = absolute_url(settings.SITE_BASE_URL, article.hero_image)

    return {
        "twitter:card": "summary_large_image" if image_url else "summary",
        "twitter:title": build_meta_title(article),
        "twitter:description": build_meta_description(article),
        "twitter:image": image_url,
    }


def build_article_meta(article: Article) -> dict:
    return {
        "title": build_meta_title(article),
        "description": build_meta_description(article),
        "canonical": build_canonical_url(article),
        "robots": build_robots(article),
        "og": build_open_graph(article),
        "twitter": build_twitter_meta(article),
    }

from __future__ import annotations
import json

from django.conf import settings

from apps.content.models import Article
from apps.seo.meta import build_canonical_url, build_meta_description, build_meta_title
from apps.seo.utils import absolute_url


def build_article_schema(article: Article) -> dict:
    schema = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": build_meta_title(article),
        "description": build_meta_description(article),
        "inLanguage": article.language,
        "mainEntityOfPage": build_canonical_url(article),
        "url": build_canonical_url(article),
        "publisher": {
            "@type": "Organization",
            "name": settings.SITE_NAME,
        },
        "dateModified": article.updated_at.isoformat(),
    }

    if article.published_at:
        schema["datePublished"] = article.published_at.isoformat()

    if article.hero_image:
        schema["image"] = [absolute_url(settings.SITE_BASE_URL, article.hero_image)]

    return schema


def build_breadcrumb_schema(items: list[tuple[str, str]]) -> dict:
    list_items = []
    for idx, (name, path_or_url) in enumerate(items, start=1):
        list_items.append(
            {
                "@type": "ListItem",
                "position": idx,
                "name": name,
                "item": absolute_url(settings.SITE_BASE_URL, path_or_url),
            }
        )

    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": list_items,
    }


def to_json_ld(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

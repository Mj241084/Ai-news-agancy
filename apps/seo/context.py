from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlencode

from django.conf import settings

from apps.content.models import Article
from apps.content.utils import render_markdown_safe
from apps.seo.utils import absolute_url, strip_html, truncate


TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"ref", "fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}

CANONICAL_QUERY_WHITELIST = {
    "about": set(),
    "contact": set(),
    "terms": set(),
    "privacy": set(),
    "auth": set(),
    "profile": set(),
    "category_index": set(),
    "home": {"page"},
    "popular": {"page"},
    "team_picks": {"page"},
    "news_list": {"page", "sort"},
    "article_list": {"page", "sort"},
    "category_detail": {"page", "sort", "type", "sub"},
    "tag_detail": {"page", "sort", "type"},
    "entity_detail": {"page"},
    "search": {"q", "page", "sort", "type"},
}

CANONICAL_QUERY_DEFAULTS = {
    "home": {"page": "1"},
    "popular": {"page": "1"},
    "team_picks": {"page": "1"},
    "news_list": {"page": "1", "sort": "latest"},
    "article_list": {"page": "1", "sort": "latest"},
    "category_detail": {"page": "1", "sort": "latest", "type": "all", "sub": "1"},
    "tag_detail": {"page": "1", "sort": "latest", "type": "all"},
    "entity_detail": {"page": "1"},
    "search": {"page": "1", "sort": "latest", "type": "all"},
}

DEFAULT_TITLES = {
    "home": "صفحه اصلی",
    "popular": "محبوب‌ترین مطالب",
    "team_picks": "پیشنهادات تیم",
    "category_index": "دسته‌بندی‌ها",
    "news_list": "اخبار",
    "article_list": "مقالات",
    "search": "جستجو",
    "auth": "ورود و ثبت‌نام",
    "profile": "پروفایل کاربری",
    "about": "درباره ما",
    "contact": "تماس با ما",
    "terms": "قوانین و مقررات",
    "privacy": "حریم خصوصی",
}

DEFAULT_DESCRIPTIONS = {
    "home": "آخرین اخبار و مقالات هوش مصنوعی",
    "popular": "محبوب‌ترین و پربازدیدترین مطالب سایت",
    "team_picks": "مطالب منتخب تیم تحریریه",
    "category_index": "مرور مطالب بر اساس دسته‌بندی‌ها",
    "news_list": "آخرین اخبار هوش مصنوعی",
    "article_list": "مقالات تحلیلی و آموزشی هوش مصنوعی",
    "search": "نتایج جستجو در اخبار و مقالات هوش مصنوعی",
    "auth": "ورود به حساب کاربری یا ثبت‌نام با ایمیل",
    "profile": "مدیریت اطلاعات حساب کاربری",
    "about": "اطلاعاتی درباره تیم و هدف‌های این رسانه.",
    "contact": "راه‌های ارتباط با تیم تحریریه و پشتیبانی سایت.",
    "terms": "قوانین و شرایط استفاده از سایت.",
    "privacy": "سیاست‌های حفظ حریم خصوصی کاربران.",
}

NOINDEX_PAGE_TYPES = {"search", "auth", "profile"}
NOINDEX_SORTS = {"popular", "team"}
ARTICLE_DETAIL_PAGE_TYPES = {"article_detail", "content_detail"}


def _obj_get(obj, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _article_description(article_obj) -> str:
    seo_description = (_obj_get(article_obj, "seo_description", "") or "").strip()
    if seo_description:
        return seo_description

    excerpt = (_obj_get(article_obj, "excerpt", "") or "").strip()
    if excerpt:
        return truncate(strip_html(excerpt), 160)

    body = (_obj_get(article_obj, "body", "") or "").strip()
    if not body:
        return ""
    body_html = render_markdown_safe(body)
    return truncate(strip_html(body_html), 160)


def _normalize_meta_robots(raw_value: str) -> str | None:
    tokens = [token.strip().lower() for token in (raw_value or "").split(",") if token.strip()]
    if not tokens:
        return None

    index_token = "noindex" if "noindex" in tokens else ("index" if "index" in tokens else None)
    follow_token = "nofollow" if "nofollow" in tokens else ("follow" if "follow" in tokens else None)

    if not index_token or not follow_token:
        return None
    return f"{index_token},{follow_token}"


def clean_querydict_for_canonical(
    querydict,
    allowlist: set[str] | None = None,
    *,
    defaults: dict[str, str] | None = None,
) -> str:
    allowed = None if allowlist is None else set(allowlist)
    normalized_defaults = {str(key): str(value) for key, value in (defaults or {}).items()}
    pairs: list[tuple[str, str]] = []

    for key in sorted(querydict.keys()):
        lowered = key.lower()
        if lowered.startswith(TRACKING_PREFIXES) or lowered in TRACKING_KEYS:
            continue
        if allowed is not None and key not in allowed:
            continue
        values = querydict.getlist(key)
        for value in values:
            value = (value or "").strip()
            if value:
                if key == "page" and value == "1":
                    continue
                default_value = normalized_defaults.get(key)
                if default_value is not None and value == default_value:
                    continue
                pairs.append((key, value))

    return urlencode(pairs, doseq=True)


def _build_canonical_url(request, *, page_type: str, obj=None, extras: dict | None = None) -> str:
    extras = extras or {}
    site_base = settings.SITE_BASE_URL

    if page_type in ARTICLE_DETAIL_PAGE_TYPES:
        canonical_path = (_obj_get(obj, "canonical_path", "") or "").strip()
        if not canonical_path:
            url_from_obj = _obj_get(obj, "url", "")
            if url_from_obj:
                canonical_path = url_from_obj
            elif hasattr(obj, "get_absolute_url"):
                canonical_path = obj.get_absolute_url()
            else:
                canonical_path = request.path
        return absolute_url(site_base, canonical_path)

    path = (extras.get("canonical_path") or request.path or "/").strip()
    if "canonical_allowlist" in extras:
        query_allowlist = extras.get("canonical_allowlist")
    else:
        query_allowlist = CANONICAL_QUERY_WHITELIST.get(page_type, set())

    if "canonical_defaults" in extras:
        query_defaults = extras.get("canonical_defaults")
    else:
        query_defaults = CANONICAL_QUERY_DEFAULTS.get(page_type, {})
    query = clean_querydict_for_canonical(
        request.GET,
        allowlist=query_allowlist,
        defaults=query_defaults,
    )

    canonical_url = absolute_url(site_base, path)
    if query:
        canonical_url = f"{canonical_url}?{query}"
    return canonical_url


def _build_breadcrumb_jsonld(items: list[tuple[str, str]]) -> dict:
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


def _build_article_jsonld(*, article_obj, canonical_url: str, description: str, image_url: str) -> dict:
    content_type = _obj_get(article_obj, "content_type")
    schema_type = "NewsArticle" if content_type == Article.CONTENT_SHORT_NEWS else "Article"

    published_at = _obj_get(article_obj, "published_at")
    updated_at = _obj_get(article_obj, "updated_at")

    schema = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "headline": (_obj_get(article_obj, "seo_title") or _obj_get(article_obj, "title") or "").strip(),
        "description": description,
        "mainEntityOfPage": canonical_url,
        "url": canonical_url,
        "author": {
            "@type": "Organization",
            "name": settings.SITE_NAME,
        },
        "publisher": {
            "@type": "Organization",
            "name": settings.SITE_NAME,
            "logo": {
                "@type": "ImageObject",
                "url": absolute_url(settings.SITE_BASE_URL, settings.PUBLISHER_LOGO_URL),
            },
        },
    }
    if image_url:
        schema["image"] = [image_url]
    if published_at:
        schema["datePublished"] = published_at.isoformat()
    if updated_at:
        schema["dateModified"] = updated_at.isoformat()
    return schema


def build_seo_context(request, *, page_type: str, obj=None, extras: dict | None = None) -> dict:
    extras = extras or {}

    site_name = settings.SITE_NAME
    default_og_image = absolute_url(settings.SITE_BASE_URL, settings.DEFAULT_OG_IMAGE_URL)

    raw_title = (extras.get("title") or "").strip()
    raw_description = (extras.get("description") or "").strip()

    if page_type in ARTICLE_DETAIL_PAGE_TYPES:
        title = raw_title or (_obj_get(obj, "seo_title") or _obj_get(obj, "title") or "").strip()
        description = raw_description or _article_description(obj)
    elif page_type in {"category_detail", "tag_detail", "entity_detail"}:
        name = (_obj_get(obj, "title") or _obj_get(obj, "name") or "").strip()
        title = raw_title or (f"{name} | {site_name}" if name else site_name)
        description = raw_description or (
            (_obj_get(obj, "description") or "").strip() or (f"مطالب مرتبط با {name}" if name else "")
        )
    else:
        page_title = DEFAULT_TITLES.get(page_type, "")
        title = raw_title or (f"{page_title} | {site_name}" if page_title else site_name)
        description = raw_description or DEFAULT_DESCRIPTIONS.get(page_type, "")

    canonical_url = _build_canonical_url(request, page_type=page_type, obj=obj, extras=extras)

    sort_value = (extras.get("sort") or request.GET.get("sort") or "").strip().lower()
    robots = (extras.get("robots") or "").strip()
    if not robots:
        robots = "index,follow"
        if page_type in NOINDEX_PAGE_TYPES or sort_value in NOINDEX_SORTS:
            robots = "noindex,follow"

    if obj is not None and _obj_get(obj, "is_indexable", None) is False:
        robots = "noindex,follow"

    if page_type in ARTICLE_DETAIL_PAGE_TYPES:
        manual_robots = _normalize_meta_robots(_obj_get(obj, "meta_robots", ""))
        if manual_robots:
            robots = manual_robots

        # Force posts to be noindex (avoid indexing short editorial posts)
        if _obj_get(obj, "content_type") == Article.CONTENT_POST:
            robots = "noindex,follow"

    og_type = extras.get("og_type") or ("article" if page_type in ARTICLE_DETAIL_PAGE_TYPES else "website")
    og_image = extras.get("og_image")
    if not og_image and page_type in ARTICLE_DETAIL_PAGE_TYPES:
        hero_image = _obj_get(obj, "hero_image")
        if hero_image:
            og_image = absolute_url(settings.SITE_BASE_URL, hero_image)
    og_image = absolute_url(settings.SITE_BASE_URL, og_image) if og_image else default_og_image

    twitter_card = "summary_large_image" if og_image else "summary"
    viewport = extras.get("viewport") or (
        "width=device-width, initial-scale=1" if page_type in ARTICLE_DETAIL_PAGE_TYPES else "width=1200"
    )

    jsonld_items = list(extras.get("jsonld") or [])
    if page_type in ARTICLE_DETAIL_PAGE_TYPES:
        jsonld_items.append(
            _build_article_jsonld(
                article_obj=obj,
                canonical_url=canonical_url,
                description=description,
                image_url=og_image,
            )
        )
        breadcrumbs = [("خانه", "/")]
        categories = _obj_get(obj, "categories", []) or []
        if categories:
            primary_category = categories[0]
            category_name = (primary_category.get("title") or primary_category.get("name") or "").strip()
            category_url = primary_category.get("url") or ""
            if category_name and category_url:
                breadcrumbs.append((category_name, category_url))
        article_title = (_obj_get(obj, "title") or "").strip()
        if article_title:
            breadcrumbs.append((article_title, canonical_url))
        if len(breadcrumbs) >= 2:
            jsonld_items.append(_build_breadcrumb_jsonld(breadcrumbs))

    for breadcrumb_items in extras.get("breadcrumb_items", []) or []:
        if breadcrumb_items:
            jsonld_items.append(_build_breadcrumb_jsonld(breadcrumb_items))

    return {
        "title": title,
        "description": description,
        "canonical_url": canonical_url,
        "canonical": canonical_url,
        "robots": robots,
        "viewport": viewport,
        "og": {
            "title": title,
            "description": description,
            "url": canonical_url,
            "type": og_type,
            "image": og_image,
            "site_name": site_name,
            "locale": "fa_IR",
        },
        "twitter": {
            "card": twitter_card,
            "title": title,
            "description": description,
            "image": og_image,
        },
        "jsonld": jsonld_items,
        "jsonld_serialized": [
            json.dumps(item, ensure_ascii=False, separators=(",", ":"))
            for item in jsonld_items
        ],
    }

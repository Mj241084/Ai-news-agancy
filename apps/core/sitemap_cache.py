from __future__ import annotations

from django.core.cache import cache


SITEMAP_XML_CACHE_KEY = "sitemap_xml:v1"
SITEMAP_INDEX_CACHE_KEY = "sitemap_index_xml:v1"
SITEMAP_CACHE_TIMEOUT = 60 * 60 * 6


def invalidate_sitemap_cache() -> None:
    cache.delete(SITEMAP_XML_CACHE_KEY)
    cache.delete(SITEMAP_INDEX_CACHE_KEY)


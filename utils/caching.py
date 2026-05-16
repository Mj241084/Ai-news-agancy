from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache


def make_cache_key(prefix: str, **params) -> str:
    version = getattr(settings, "DATA_CACHE_VERSION", "v1")
    cleaned = {
        str(key): "" if value is None else str(value)
        for key, value in sorted(params.items(), key=lambda item: item[0])
    }
    query = urlencode(cleaned, doseq=False)
    if query:
        return f"{prefix}:{version}:{query}"
    return f"{prefix}:{version}"


def get_or_set_cached(key: str, timeout: int, builder):
    cached = cache.get(key)
    if cached is not None:
        return cached
    value = builder()
    cache.set(key, value, timeout=timeout)
    return value

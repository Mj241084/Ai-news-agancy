from __future__ import annotations
from html import unescape
from urllib.parse import urljoin

from django.utils.html import strip_tags


def strip_html(value: str) -> str:
    return " ".join(unescape(strip_tags(value or "")).split())


def truncate(value: str, length: int = 160) -> str:
    value = (value or "").strip()
    if len(value) <= length:
        return value
    return value[: max(length - 1, 1)].rstrip() + "…"


def absolute_url(base_url: str, path_or_url: str) -> str:
    if not path_or_url:
        return base_url.rstrip("/")
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return urljoin(base_url.rstrip("/") + "/", path_or_url.lstrip("/"))

from __future__ import annotations

from datetime import datetime

from django import template
from django.urls import reverse
from django.utils import timezone

register = template.Library()
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


@register.filter
def content_url(item):
    slug = None
    if isinstance(item, dict):
        slug = item.get("slug")
    else:
        slug = getattr(item, "slug", None)

    if not slug:
        return "#"

    return reverse("content:detail", args=[slug])


@register.filter
def dict_get(data, key):
    if not isinstance(data, dict):
        return None
    return data.get(key)


def _fa_number(value: int) -> str:
    return str(int(value)).translate(_PERSIAN_DIGITS)


@register.filter
def humanize_fa_time(value):
    if not value:
        return ""

    if not isinstance(value, datetime):
        return value

    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())

    now = timezone.localtime(timezone.now())
    published_at = timezone.localtime(value)

    if published_at > now:
        return "لحظاتی دیگر"

    seconds = int((now - published_at).total_seconds())
    minutes = seconds // 60
    hours = minutes // 60
    day_diff = (now.date() - published_at.date()).days

    if day_diff == 0:
        if hours < 1:
            if minutes < 1:
                return "لحظاتی پیش"
            return f"{_fa_number(minutes)} دقیقه پیش"
        if hours <= 6:
            return f"{_fa_number(hours)} ساعت پیش"
        return "امروز"

    if day_diff == 1:
        return "دیروز"

    if day_diff < 7:
        return f"{_fa_number(day_diff)} روز پیش"

    if day_diff < 30:
        weeks = max(day_diff // 7, 1)
        if weeks == 1:
            return "هفته پیش"
        return f"{_fa_number(weeks)} هفته پیش"

    return published_at.strftime("%Y/%m/%d").translate(_PERSIAN_DIGITS)

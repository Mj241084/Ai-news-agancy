from __future__ import annotations

from datetime import date, datetime

from django import template
from django.utils import timezone

register = template.Library()

_GREGORIAN_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_JALALI_DAYS_IN_MONTH = (31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29)


def _gregorian_to_jalali_parts(value: date) -> tuple[int, int, int]:
    gy = value.year - 1600
    gm = value.month - 1
    gd = value.day - 1

    g_day_no = (
        365 * gy
        + (gy + 3) // 4
        - (gy + 99) // 100
        + (gy + 399) // 400
        + gd
    )
    g_day_no += sum(_GREGORIAN_DAYS_IN_MONTH[:gm])

    is_leap_gregorian = ((value.year % 4 == 0 and value.year % 100 != 0) or value.year % 400 == 0)
    if gm > 1 and is_leap_gregorian:
        g_day_no += 1

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    jm = 0
    for month_days in _JALALI_DAYS_IN_MONTH:
        if j_day_no < month_days:
            break
        j_day_no -= month_days
        jm += 1

    return jy, jm + 1, j_day_no + 1


def _format_jalali(jy: int, jm: int, jd: int, dt: datetime | None, fmt: str | None) -> str:
    if not fmt:
        fmt = "%Y/%m/%d %H:%M" if dt else "%Y/%m/%d"

    replacements = {
        "%Y": f"{jy:04d}",
        "%m": f"{jm:02d}",
        "%d": f"{jd:02d}",
        "%H": f"{dt.hour:02d}" if dt else "00",
        "%M": f"{dt.minute:02d}" if dt else "00",
        "%S": f"{dt.second:02d}" if dt else "00",
    }
    output = fmt
    for token, value in replacements.items():
        output = output.replace(token, value)
    return output


@register.filter
def to_jalali(g_date, strftime=None):
    if g_date is None:
        return "-"

    if isinstance(g_date, datetime):
        if timezone.is_naive(g_date):
            g_date = timezone.make_aware(g_date, timezone.get_current_timezone())
        local_dt = timezone.localtime(g_date)
        jy, jm, jd = _gregorian_to_jalali_parts(local_dt.date())
        return _format_jalali(jy, jm, jd, local_dt, strftime)

    if isinstance(g_date, date):
        jy, jm, jd = _gregorian_to_jalali_parts(g_date)
        return _format_jalali(jy, jm, jd, None, strftime)

    return "-"


@register.simple_tag
def jalali_now(strftime=None):
    return to_jalali(timezone.localtime(timezone.now()), strftime or "%Y/%m/%d")

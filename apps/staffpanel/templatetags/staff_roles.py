from __future__ import annotations
from django import template

from apps.staffpanel.mixins import user_in_group

register = template.Library()


@register.filter(name="has_group")
def has_group(user, group_name: str) -> bool:
    """Template helper: {% if request.user|has_group:'editorial_admins' %}."""
    try:
        return user_in_group(user, group_name)
    except Exception:
        return False

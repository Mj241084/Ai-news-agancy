from __future__ import annotations
from uuid import uuid4

from django.utils.text import slugify


def unique_slugify(
    instance,
    value: str,
    slug_field_name: str = "slug",
    queryset=None,
    allow_unicode: bool = True,
    max_length: int | None = None,
) -> str:
    """Set and return a unique slug on ``instance`` for ``value``."""
    slug_field = instance._meta.get_field(slug_field_name)
    max_length = max_length or slug_field.max_length

    base_slug = slugify(value, allow_unicode=allow_unicode)[:max_length]
    if not base_slug:
        base_slug = uuid4().hex[: min(max_length, 12)]

    model_class = instance.__class__
    qs = queryset if queryset is not None else model_class._default_manager.all()
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)

    slug = base_slug
    counter = 2
    while qs.filter(**{slug_field_name: slug}).exists():
        suffix = f"-{counter}"
        slug = f"{base_slug[: max_length - len(suffix)]}{suffix}"
        counter += 1

    setattr(instance, slug_field.attname, slug)
    return slug

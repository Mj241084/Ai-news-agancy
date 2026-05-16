from __future__ import annotations
from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.content"
    label = "content"

    def ready(self):
        from apps.content import signals  # noqa: F401

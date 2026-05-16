from __future__ import annotations
from django.apps import AppConfig


class EntitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.entities"
    label = "entities"

    def ready(self):
        from apps.entities import signals  # noqa: F401
    label = "entities"

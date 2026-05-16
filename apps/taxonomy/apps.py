from __future__ import annotations
from django.apps import AppConfig


class TaxonomyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.taxonomy"
    label = "taxonomy"

    def ready(self):
        from apps.taxonomy import signals  # noqa: F401

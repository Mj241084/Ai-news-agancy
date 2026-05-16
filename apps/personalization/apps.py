from __future__ import annotations
from django.apps import AppConfig


class PersonalizationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.personalization"
    label = "personalization"

from __future__ import annotations
from django.contrib import admin

from apps.editorial.models import PromptTemplate, WritingRuleSet


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "key", "language", "status", "is_active", "updated_at")
    search_fields = ("title", "key", "body")
    list_filter = ("status", "is_active", "language")


@admin.register(WritingRuleSet)
class WritingRuleSetAdmin(admin.ModelAdmin):
    list_display = ("title", "key", "scenario", "priority", "status", "is_active", "updated_at")
    search_fields = ("title", "key", "scenario", "body")
    list_filter = ("status", "is_active", "scenario")
    filter_horizontal = ("categories", "tags", "prompts")

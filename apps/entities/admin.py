from __future__ import annotations
from django.contrib import admin

from apps.entities.models import Entity, RankingEntry, RankingList


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "is_active", "is_indexable")
    list_filter = ("type", "is_active", "is_indexable")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


class RankingEntryInline(admin.TabularInline):
    model = RankingEntry
    extra = 0


@admin.register(RankingList)
class RankingListAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "is_active", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("title",)
    inlines = [RankingEntryInline]

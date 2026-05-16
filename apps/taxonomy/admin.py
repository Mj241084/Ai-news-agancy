from __future__ import annotations
from django.contrib import admin

from apps.taxonomy.models import Category, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "parent", "is_active", "is_indexable", "order")
    list_filter = ("is_active", "is_indexable", "parent")
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "is_indexable")
    list_filter = ("is_active", "is_indexable")
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}

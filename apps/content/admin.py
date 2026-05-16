from __future__ import annotations
from django.contrib import admin

from apps.content.models import (
    Article,
    ArticleComment,
    ArticleCategory,
    ArticleEntity,
    ArticleSource,
    ArticleTag,
    Source,
)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "content_type", "is_team_pick", "published_at")
    search_fields = ("title", "excerpt")
    list_filter = ("status", "content_type", "is_team_pick", "published_at")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ArticleCategory)
class ArticleCategoryAdmin(admin.ModelAdmin):
    list_display = ("article", "category", "is_primary", "weight")
    list_filter = ("is_primary", "category")
    search_fields = ("article__title", "category__title")


@admin.register(ArticleComment)
class ArticleCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "article", "user", "is_visible", "created_at")
    list_filter = ("is_visible", "created_at")
    search_fields = ("article__title", "user__username", "text")


@admin.register(ArticleTag)
class ArticleTagAdmin(admin.ModelAdmin):
    list_display = ("article", "tag")
    search_fields = ("article__title", "tag__title")


@admin.register(ArticleEntity)
class ArticleEntityAdmin(admin.ModelAdmin):
    list_display = ("article", "entity", "role", "importance")
    list_filter = ("role",)
    search_fields = ("article__title", "entity__name")


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("name", "url")


@admin.register(ArticleSource)
class ArticleSourceAdmin(admin.ModelAdmin):
    list_display = ("article", "source", "confidence")
    search_fields = ("article__title", "source__name", "original_url")

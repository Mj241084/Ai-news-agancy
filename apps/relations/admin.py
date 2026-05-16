from __future__ import annotations
from django.contrib import admin

from apps.relations.models import ArticleRelation


@admin.register(ArticleRelation)
class ArticleRelationAdmin(admin.ModelAdmin):
    list_display = ("article_a", "article_b", "score", "algo_version", "updated_at")
    search_fields = ("article_a__title", "article_b__title")
    list_filter = ("algo_version", "updated_at")

from __future__ import annotations

from django.contrib.sitemaps import Sitemap

from apps.content.models import Article
from apps.entities.models import Entity
from apps.taxonomy.models import Category, Tag


class ArticlesSitemap(Sitemap):
    changefreq = "hourly"
    priority = 0.9

    def items(self):
        return Article.objects.filter(
            status=Article.STATUS_PUBLISHED,
            published_at__isnull=False,
        ).exclude(
            content_type=Article.CONTENT_POST,
        ).order_by("-published_at")

    def lastmod(self, obj):
        return obj.updated_at or obj.published_at


class CategoriesSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return Category.objects.filter(
            is_active=True,
            is_indexable=True,
        ).order_by("order", "title")


class TagsSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.5

    def items(self):
        return Tag.objects.filter(
            is_active=True,
            is_indexable=True,
        ).order_by("title")


class EntitiesSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return Entity.objects.filter(
            is_active=True,
            is_indexable=True,
        ).order_by("name")


sitemaps = {
    "articles": ArticlesSitemap,
    "categories": CategoriesSitemap,
    "tags": TagsSitemap,
    "entities": EntitiesSitemap,
}


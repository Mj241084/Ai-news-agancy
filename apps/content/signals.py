from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.content.models import Article
from apps.core.sitemap_cache import invalidate_sitemap_cache
from apps.content.cache_invalidation import invalidate_article_cache


@receiver(post_save, sender=Article)
def invalidate_sitemap_on_article_save(sender, instance: Article, **kwargs):
    invalidate_sitemap_cache()
    # Ensure article pages reflect admin-side updates (SEO fields, images, etc.)
    if instance.status == Article.STATUS_PUBLISHED:
        invalidate_article_cache(instance)


@receiver(post_delete, sender=Article)
def invalidate_sitemap_on_article_delete(sender, instance: Article, **kwargs):
    invalidate_sitemap_cache()


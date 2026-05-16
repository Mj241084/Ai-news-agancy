from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.taxonomy.cache_invalidation import (
    invalidate_taxonomy_on_category_change,
    invalidate_taxonomy_on_tag_change,
)
from apps.taxonomy.models import Category, Tag


@receiver(pre_save, sender=Category)
def remember_category_previous_state(sender, instance: Category, **kwargs):
    if not instance.pk:
        return
    previous = Category.objects.filter(pk=instance.pk).only("slug", "parent_id").first()
    if previous:
        instance._old_slug = previous.slug
        instance._old_parent_id = previous.parent_id


@receiver(post_save, sender=Category)
def invalidate_category_cache_on_save(sender, instance: Category, **kwargs):
    invalidate_taxonomy_on_category_change(
        instance,
        previous_slug=getattr(instance, "_old_slug", None),
        previous_parent_id=getattr(instance, "_old_parent_id", None),
    )


@receiver(post_delete, sender=Category)
def invalidate_category_cache_on_delete(sender, instance: Category, **kwargs):
    invalidate_taxonomy_on_category_change(instance, previous_slug=instance.slug)


@receiver(pre_save, sender=Tag)
def remember_tag_previous_state(sender, instance: Tag, **kwargs):
    if not instance.pk:
        return
    previous = Tag.objects.filter(pk=instance.pk).only("slug").first()
    if previous:
        instance._old_slug = previous.slug


@receiver(post_save, sender=Tag)
def invalidate_tag_cache_on_save(sender, instance: Tag, **kwargs):
    invalidate_taxonomy_on_tag_change(instance, previous_slug=getattr(instance, "_old_slug", None))


@receiver(post_delete, sender=Tag)
def invalidate_tag_cache_on_delete(sender, instance: Tag, **kwargs):
    invalidate_taxonomy_on_tag_change(instance, previous_slug=instance.slug)


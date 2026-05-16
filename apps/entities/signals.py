from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.entities.models import Entity
from apps.taxonomy.cache_invalidation import invalidate_taxonomy_on_entity_change


@receiver(pre_save, sender=Entity)
def remember_entity_previous_state(sender, instance: Entity, **kwargs):
    if not instance.pk:
        return
    previous = Entity.objects.filter(pk=instance.pk).only("type", "slug").first()
    if previous:
        instance._old_type = previous.type
        instance._old_slug = previous.slug


@receiver(post_save, sender=Entity)
def invalidate_entity_cache_on_save(sender, instance: Entity, **kwargs):
    invalidate_taxonomy_on_entity_change(
        instance,
        previous_slug=getattr(instance, "_old_slug", None),
        previous_type=getattr(instance, "_old_type", None),
    )


@receiver(post_delete, sender=Entity)
def invalidate_entity_cache_on_delete(sender, instance: Entity, **kwargs):
    invalidate_taxonomy_on_entity_change(
        instance,
        previous_slug=instance.slug,
        previous_type=instance.type,
    )

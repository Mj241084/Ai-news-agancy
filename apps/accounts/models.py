from __future__ import annotations
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.entities.models import Entity
from apps.taxonomy.models import Category, Tag


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    preferred_categories = models.ManyToManyField(Category, blank=True, related_name="preferred_by_profiles")
    preferred_entities = models.ManyToManyField(Entity, blank=True, related_name="preferred_by_profiles")
    preferred_tags = models.ManyToManyField(Tag, blank=True, related_name="preferred_by_profiles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        return f"Profile<{self.user_id}>"


class EmailOTP(models.Model):
    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["email", "-created_at"]),
            models.Index(fields=["email", "used_at", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"OTP<{self.email}>"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None
